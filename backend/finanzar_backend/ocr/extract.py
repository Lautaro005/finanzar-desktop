"""Extracción estructurada de resúmenes con JSON schema estricto.

Dos caminos con el mismo contrato de salida:
1. ``extract_with_llm`` — pide al copiloto local (Spark) un JSON estricto.
2. ``extract_heuristic`` — reglas y expresiones para texto de resumen argentino.

Cada campo conserva confianza, página, bbox y evidencia textual.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core.money import to_cents
from .glm_ocr import PageText

# --- JSON schema estricto que debe devolver el modelo -------------------
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "card",
        "brand",
        "period",
        "close_date",
        "due_date",
        "total",
        "minimum",
        "currency",
        "movements",
        "installments",
        "subscriptions",
        "charges",
    ],
    "properties": {
        "card": {"type": "string"},
        "brand": {"type": "string", "enum": ["visa", "master", "amex", "other"]},
        "period": {"type": ["string", "null"]},
        "close_date": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"]},
        "total": {"type": ["number", "null"]},
        "minimum": {"type": ["number", "null"]},
        "currency": {"type": "string"},
        "movements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["date", "description", "amount"],
                "properties": {
                    "date": {"type": ["string", "null"]},
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                    "installment_number": {"type": ["integer", "null"]},
                    "installment_total": {"type": ["integer", "null"]},
                    "currency": {"type": ["string", "null"]},
                    "category": {"type": ["string", "null"]},
                },
            },
        },
        "installments": {"type": "array", "items": {"type": "object"}},
        "subscriptions": {"type": "array", "items": {"type": "object"}},
        "charges": {"type": "array", "items": {"type": "object"}},
    },
}


@dataclass
class ExtractedField:
    key: str
    value: Any
    value_type: str = "text"
    confidence: float | None = None
    page: int | None = None
    bbox: list[float] | None = None
    evidence: str | None = None


@dataclass
class ExtractedTransaction:
    occurred_on: str
    description: str
    amount_cents: int
    currency: str = "ARS"
    installment_number: int | None = None
    installment_total: int | None = None
    kind: str = "purchase"
    category: str | None = None
    page: int | None = None
    bbox: list[float] | None = None
    confidence: float | None = None


@dataclass
class ExtractedStatement:
    fields: list[ExtractedField] = field(default_factory=list)
    transactions: list[ExtractedTransaction] = field(default_factory=list)
    installments: list[ExtractedTransaction] = field(default_factory=list)
    subscriptions: list[ExtractedTransaction] = field(default_factory=list)
    engine: str = "heuristic"
    raw_text: str = ""

    def field_map(self) -> dict[str, ExtractedField]:
        return {f.key: f for f in self.fields}


# --- utilidades de parseo ----------------------------------------------
_AMOUNT_RE = re.compile(
    r"(?P<cur>US\$|U\$S|USD|AR\$|\$)?\s?"
    r"(?P<num>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2})?)"
)
_DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_INSTALLMENT_RE = re.compile(r"(?:cuota\s*)?0?(\d{1,2})\s*/\s*0?(\d{1,2})", re.IGNORECASE)
_SUB_KEYWORDS = (
    "netflix",
    "spotify",
    "streaming",
    "suscrip",
    "adobe",
    "youtube",
    "hbo",
    "disney",
    "chatgpt",
    "icloud",
    "google one",
    "plan",
    "mensual",
)
_BRAND_KEYWORDS = {
    "visa": "visa",
    "mastercard": "master",
    "master": "master",
    "american express": "amex",
    "amex": "amex",
    "naranja": "other",
    "cabal": "other",
}


def _parse_amount(text: str) -> int | None:
    matches = list(_AMOUNT_RE.finditer(text))
    if not matches:
        return None
    # Se toma el último importe de la línea: en resúmenes el monto va al final.
    for match in reversed(matches):
        raw = match.group("num")
        try:
            return to_cents(raw)
        except Exception:
            continue
    return None


def _parse_date(text: str, reference: date | None = None) -> str | None:
    """Devuelve una fecha ISO (``YYYY-MM-DD``) o ``None``."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _find_line(text: str, keywords: tuple[str, ...]) -> tuple[str, float] | None:
    lowered = text.lower()
    for line in lowered.splitlines():
        for keyword in keywords:
            if keyword in line:
                return line, 1.0
    return None


def guess_brand(text: str) -> str:
    lowered = text.lower()
    for keyword, brand in _BRAND_KEYWORDS.items():
        if keyword in lowered:
            return brand
    return "other"


def guess_category(description: str) -> str:
    lowered = description.lower()
    table = {
        "Alimentación": ("super", "mercado", "coto", "disco", "jumbo", "dia", "carrefour", "la plaza"),
        "Transporte": ("uber", "cabify", "taxi", "sube", "peaje", "nafta", "ypf", "shell", "combustible"),
        "Salud": ("farmacia", "farmacity", "obra social", "medic", "clinica", "salud"),
        "Tecnología": ("notebook", "apple", "samsung", "compu", "celular", "tecnolog"),
        "Suscripción": _SUB_KEYWORDS,
        "Indumentaria": ("zara", "adidas", "nike", "ropa", "calzado"),
        "Hogar": ("ferreteria", "sodimac", "easy", "mueble", "hogar"),
        "Entretenimiento": ("cine", "restaurante", "bar", "delivery", "pedidos"),
    }
    for category, keywords in table.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "Sin categoría"


# --- camino heurístico --------------------------------------------------
def extract_heuristic(pages: list[PageText]) -> ExtractedStatement:
    full_text = "\n".join(page.text for page in pages)
    result = ExtractedStatement(engine="heuristic", raw_text=full_text)

    brand = guess_brand(full_text)
    currency = "USD" if re.search(r"u\$s|usd|d[óo]lares", full_text, re.IGNORECASE) else "ARS"

    total_line = _find_line(full_text, ("total a pagar", "total actual", "importe total"))
    minimum_line = _find_line(full_text, ("pago m", "minimo", "mínimo"))
    close_line = _find_line(full_text, ("cierre",))
    due_line = _find_line(full_text, ("vencimiento", "vence"))
    period_line = _find_line(full_text, ("periodo", "período", "resumen"))

    if total_line:
        total_cents = _parse_amount(total_line[0])
        result.fields.append(
            ExtractedField("total", total_cents, "money", 0.9, 1, None, total_line[0].strip())
        )
    if minimum_line:
        result.fields.append(
            ExtractedField(
                "minimum", _parse_amount(minimum_line[0]), "money", 0.8, 1, None, minimum_line[0].strip()
            )
        )
    due = _parse_date(due_line[0]) if due_line else None
    if due:
        result.fields.append(ExtractedField("due_date", due, "date", 0.85, 1, None, due_line[0].strip()))
    close = _parse_date(close_line[0]) if close_line else None
    if close:
        result.fields.append(ExtractedField("close_date", close, "date", 0.8, 1, None, close_line[0].strip()))
    if period_line and re.search(r"\d{4}-\d{2}", period_line[0]):
        result.fields.append(ExtractedField("period", None, "text", 0.5, 1, None, period_line[0].strip()))

    result.fields.append(ExtractedField("brand", brand, "text", 1.0 if brand != "other" else 0.4))
    result.fields.append(ExtractedField("currency", currency, "text", 1.0))

    # Movimientos: líneas con fecha + descripción + importe.
    for page in pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            date_value = _parse_date(line)
            if not date_value:
                continue
            # Se quita la fecha antes de buscar el importe para no confundir
            # dígitos de la fecha con el monto.
            without_date = _DATE_RE.sub(" ", line)
            amount_cents = _parse_amount(without_date)
            if not amount_cents:
                continue
            description = _AMOUNT_RE.sub(" ", without_date).strip(" -·\t:.,")
            if len(description) < 3:
                continue
            installment_match = _INSTALLMENT_RE.search(without_date)
            number = total = None
            kind = "purchase"
            if installment_match:
                number = int(installment_match.group(1))
                total = int(installment_match.group(2))
                if 1 <= number <= total <= 60:
                    kind = "installment"
                else:
                    number = total = None
            lowered = line.lower()
            if kind != "installment" and any(word in lowered for word in _SUB_KEYWORDS):
                kind = "subscription"
            transaction = ExtractedTransaction(
                occurred_on=date_value,
                description=description[:120],
                amount_cents=amount_cents,
                currency="USD" if re.search(r"us\$|u\$s|usd", lowered) else currency,
                installment_number=number,
                installment_total=total,
                kind=kind,
                category=guess_category(description),
                page=page.number,
                confidence=0.7 if installment_match else 0.65,
            )
            if kind == "installment":
                result.installments.append(transaction)
            elif kind == "subscription":
                result.subscriptions.append(transaction)
            else:
                result.transactions.append(transaction)
    return result


# --- camino LLM ---------------------------------------------------------
def build_extraction_prompt(text: str) -> str:
    schema_text = json.dumps(EXTRACTION_SCHEMA, ensure_ascii=False)
    return (
        "Sos un extractor de resúmenes de tarjeta de crédito argentinos. "
        "Devolvé ÚNICAMENTE un JSON válido que cumpla exactamente este schema, sin texto adicional. "
        "Usá null cuando no puedas determinarlo con certeza. No inventes importes.\n\n"
        f"SCHEMA:\n{schema_text}\n\nTEXTO DEL RESUMEN:\n{text[:12000]}"
    )


def parse_llm_json(payload: str) -> dict[str, Any] | None:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def from_llm_payload(payload: dict[str, Any], pages: list[PageText]) -> ExtractedStatement:
    result = ExtractedStatement(engine="llm", raw_text="\n".join(p.text for p in pages))
    currency = str(payload.get("currency") or "ARS")

    def add_field(key: str, value: Any, value_type: str, confidence: float) -> None:
        result.fields.append(ExtractedField(key, value, value_type, confidence, 1, None, None))

    add_field("card", payload.get("card"), "text", 0.9)
    add_field("brand", payload.get("brand") or "other", "text", 0.85)
    add_field("period", payload.get("period"), "text", 0.8)
    add_field("close_date", payload.get("close_date"), "date", 0.8)
    add_field("due_date", payload.get("due_date"), "date", 0.85)
    add_field("currency", currency, "text", 0.9)
    total = payload.get("total")
    minimum = payload.get("minimum")
    if total is not None:
        add_field("total", to_cents(str(total)) if not isinstance(total, int) else total * 100, "money", 0.85)
    if minimum is not None:
        add_field(
            "minimum", to_cents(str(minimum)) if not isinstance(minimum, int) else minimum * 100, "money", 0.8
        )

    def to_transaction(item: dict[str, Any], kind: str) -> ExtractedTransaction | None:
        amount = item.get("amount")
        if amount is None:
            return None
        try:
            cents = amount * 100 if isinstance(amount, int) else to_cents(str(amount))
        except Exception:
            return None
        occurred = item.get("date") or date.today().isoformat()
        return ExtractedTransaction(
            occurred_on=occurred,
            description=str(item.get("description", ""))[:120],
            amount_cents=int(cents),
            currency=item.get("currency") or currency,
            installment_number=item.get("installment_number"),
            installment_total=item.get("installment_total"),
            kind=kind,
            category=item.get("category") or guess_category(str(item.get("description", ""))),
            page=1,
            confidence=0.7,
        )

    for item in payload.get("movements", []) or []:
        tx = to_transaction(item, "purchase")
        if tx:
            if tx.installment_total and tx.installment_number:
                tx.kind = "installment"
                result.installments.append(tx)
            elif any(word in tx.description.lower() for word in _SUB_KEYWORDS):
                tx.kind = "subscription"
                result.subscriptions.append(tx)
            else:
                result.transactions.append(tx)
    for item in payload.get("installments", []) or []:
        tx = to_transaction(item, "installment")
        if tx:
            result.installments.append(tx)
    for item in payload.get("subscriptions", []) or []:
        tx = to_transaction(item, "subscription")
        if tx:
            result.subscriptions.append(tx)
    return result
