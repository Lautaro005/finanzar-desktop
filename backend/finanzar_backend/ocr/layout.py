"""Extracción por layout para resúmenes con capa de texto.

Los resúmenes de tarjeta argentinos (American Express, Visa, Mastercard) tienen
**dos columnas de importes**: pesos y dólares. En el texto plano las columnas se
pierden —el lector solo ve números sueltos— y todo termina marcado como dólares
en cuanto el documento menciona la palabra "dólares".

Este módulo usa la posición horizontal de cada palabra (PyMuPDF) para saber a qué
columna pertenece cada importe, y además reconoce las percepciones e impuestos
que se cobran **en pesos** por las compras en dólares (IVA RG 4240, IIBB
PERCEP-BSAS, DB.RG 5617, impuesto de sellos, etc.).

Cuando el PDF no tiene capa de texto (escaneado) no hay coordenadas y se
devuelve ``None``: el pipeline cae al texto del OCR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from .extract import ExtractedField, ExtractedStatement, ExtractedTransaction, guess_category
from .pdf import PageWords

# --- patrones -----------------------------------------------------------
_AMOUNT_TOKEN = re.compile(r"^\(?-?\$?(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?)\)?-?$")
_DATE_DIGITS = re.compile(r"^(?P<d>\d{1,2})[./\-\s](?P<m>\d{1,2})[./\-\s](?P<y>\d{2,4})$")
_DATE_TEXT = re.compile(
    r"^(?P<d>\d{1,2})[./\-\s]?(?P<mon>[A-Za-zÁÉÍÓÚáéíóúñ]{3,})\.?[./\-\s]+(?P<y>\d{2,4})$"
)

_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
    "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
    "jan": 1, "apr": 4, "aug": 8, "dec": 12,
}

# Renglones que no son consumos: totales, saldos, textos legales y planes.
_SKIP_KEYWORDS = (
    "saldo anterior",
    "saldo actual",
    "su pago",
    "pago minimo",
    "pago min",
    "total consumos",
    "proximo cierre",
    "proximo vencimiento",
    "proximo vto",
    "cierre anterior",
    "cierre actual",
    "cierre",
    "vencimiento anterior",
    "vencimiento",
    "vto.",
    "limite",
    "cft",
    "tna",
    "tea",
    "cuotas de",
    "condiciones vigentes",
    "llame",
    "comision",
    "usted puede",
    "http",
    "sujeto al",
    "cancelacion",
    "ejemplo",
    "adelanto",
    "transparencia",
    "bcra",
    "renovacion",
    "reposicion",
    "gestion ",
    "regimen",
    "prestaciones",
    "express plan",
    "las nuevas comisiones",
    "reintegrado",
    "devengan",
    "costo financiero",
)

# Percepciones e impuestos sobre consumos en dólares (siempre en pesos).
_TAX_KEYWORDS = (
    "impuesto",
    "percep",
    "iibb",
    "ingresos brutos",
    "iva rg",
    "db.rg",
    "db rg",
    "sellos",
    "rg 5617",
    "rg 4240",
    "rg 5463",
    "retencion",
    "dev.imp",
    "dev. imp",
)

_SUBSCRIPTION_KEYWORDS = (
    "netflix",
    "spotify",
    "streaming",
    "suscrip",
    "adobe",
    "youtube",
    "hbo",
    "disney",
    "chatgpt",
    "openai",
    "icloud",
    "google one",
    "apple.com/bill",
    "itunes",
    "microsoft 365",
    "dropbox",
)

_CURRENCY_MARKERS = {"usd", "u$s", "us$", "dolares", "dls", "u$s."}


@dataclass
class _Token:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _amount_cents(text: str) -> int | None:
    """Convierte ``13.188,79`` o ``1,99`` a centavos; ``None`` si no es importe."""
    raw_text = text.strip()
    match = _AMOUNT_TOKEN.match(raw_text)
    if not match:
        return None
    raw = match.group("num")
    if "," not in raw and "." not in raw:
        # Un entero pelado ("26", "01") es el año o el día de una fecha, no un
        # importe: los importes del resumen siempre traen separador.
        return None
    negative = raw_text.startswith(("-", "(")) or raw_text.endswith("-")
    if "," in raw:
        integer, decimals = raw.rsplit(",", 1)
        integer = integer.replace(".", "")
    else:
        # Sin coma decimal: puede ser miles ("39.000") o un entero.
        integer, decimals = raw.replace(".", ""), "00"
    if not integer.isdigit():
        return None
    cents = int(integer) * 100 + int((decimals + "00")[:2])
    return -cents if negative else cents


def _parse_date(text: str) -> str | None:
    """``03.09.26`` o ``01 Oct 26`` a ISO; ``None`` si no es fecha."""
    match = _DATE_DIGITS.match(text.strip())
    if match:
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    match = _DATE_TEXT.match(text.strip())
    if match:
        day = int(match.group("d"))
        month = _MONTHS.get(match.group("mon")[:3].lower())
        year = int(match.group("y"))
        if year < 100:
            year += 2000
        if month:
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                return None
    return None


def _lines(words: list[dict[str, object]]) -> list[list[_Token]]:
    """Agrupa palabras por (bloque, línea) y las ordena de izquierda a derecha."""
    grouped: dict[tuple[int, int], list[_Token]] = {}
    for word in words:
        key = (int(word["block"]), int(word["line"]))
        grouped.setdefault(key, []).append(
            _Token(
                text=str(word["text"]),
                x0=float(word["x0"]),
                y0=float(word["y0"]),
                x1=float(word["x1"]),
                y1=float(word["y1"]),
            )
        )
    ordered = [sorted(tokens, key=lambda t: t.x0) for tokens in grouped.values()]
    return sorted(ordered, key=lambda tokens: (min(t.y0 for t in tokens), min(t.x0 for t in tokens)))


def _phrases(line: list[_Token]) -> list[_Token]:
    """Une fechas partidas en varias palabras ("01 Oct 26") en un solo token."""
    phrases: list[_Token] = []
    index = 0
    while index < len(line):
        merged = None
        for width in (3, 2):
            window = line[index : index + width]
            if len(window) < width:
                continue
            gaps = [window[i + 1].x0 - window[i].x1 for i in range(width - 1)]
            if any(gap > 8 for gap in gaps):
                continue
            text = " ".join(t.text for t in window)
            if _parse_date(text) is not None:
                merged = _Token(
                    text=text,
                    x0=min(t.x0 for t in window),
                    y0=min(t.y0 for t in window),
                    x1=max(t.x1 for t in window),
                    y1=max(t.y1 for t in window),
                )
                break
        if merged is not None:
            phrases.append(merged)
            index += width
        else:
            phrases.append(line[index])
            index += 1
    return phrases


def _is_kind(token: _Token, kind: str) -> bool:
    return _parse_date(token.text) is not None if kind == "date" else _amount_cents(token.text) is not None


def _find_label_line(lines: list[list[_Token]], needle: str, *, exclude: tuple[str, ...] = ()) -> list[_Token] | None:
    wanted = _normalize(needle)
    # Preferencia: coincidencia exacta del renglón; si no, que lo contenga.
    for line in lines:
        text = _normalize(" ".join(t.text for t in line))
        if text == wanted and not any(word in text for word in exclude):
            return line
    for line in lines:
        text = _normalize(" ".join(t.text for t in line))
        if wanted in text and not any(word in text for word in exclude):
            return line
    return None


def _value_for(line: list[_Token], needle: str, kind: str, lines: list[list[_Token]]) -> _Token | None:
    """Valor asociado a una etiqueta de encabezado.

    Busca a la derecha en la misma línea (``CIERRE ACTUAL: 01 Oct 26``) y, si no
    hay, el token más cercano por debajo alineado en la misma columna (las tablas
    de encabezado ponen la etiqueta arriba y el valor abajo).
    """
    wanted = _normalize(needle)
    anchor = next(
        (t for t in line if wanted.startswith(_normalize(t.text)) or _normalize(t.text) == wanted),
        line[0],
    )
    same_line = [t for t in _phrases(line) if t.x0 > anchor.x1 - 1 and _is_kind(t, kind)]
    if same_line:
        return min(same_line, key=lambda t: t.x0)
    below = [
        t
        for other in lines
        for t in _phrases(other)
        if t.y0 >= anchor.y0 - 1
        and t.y0 - anchor.y0 < 120
        and abs(t.cx - anchor.cx) < 55
        and _is_kind(t, kind)
    ]
    if below:
        return min(below, key=lambda t: (t.y0 - anchor.y0, abs(t.cx - anchor.cx)))
    return None


def _line_in_region(line: list[_Token], page: PageWords, region: dict[str, float]) -> bool:
    """¿El renglón cae dentro de la zona marcada? (las zonas son por página)."""
    if int(region.get("page", 1)) != page.number:
        return False
    y0 = min(token.y0 for token in line)
    y1 = max(token.y1 for token in line)
    x0 = min(token.x0 for token in line)
    x1 = max(token.x1 for token in line)
    # Se exige que el renglón esté contenido: así una zona marcada sobre una
    # fila no arrastra las de arriba y abajo.
    return (
        y0 >= float(region["y0"]) - 2
        and y1 <= float(region["y1"]) + 2
        and x1 >= float(region["x0"]) - 2
        and x0 <= float(region["x1"]) + 2
    )


def _kind_for(description: str) -> str:
    lowered = description.lower()
    if any(keyword in lowered for keyword in _TAX_KEYWORDS):
        return "tax"
    if any(keyword in lowered for keyword in _SUBSCRIPTION_KEYWORDS):
        return "subscription"
    return "purchase"


def _guess_brand(text: str) -> str:
    lowered = text.lower()
    for keyword, brand in (
        ("american express", "amex"),
        ("amex", "amex"),
        ("mastercard", "master"),
        ("visa", "visa"),
        ("naranja", "other"),
        ("cabal", "other"),
    ):
        if keyword in lowered:
            return brand
    return "other"


def parse_layout(pages: list[PageWords], region: dict[str, float] | None = None) -> ExtractedStatement | None:
    """Extrae el resumen usando las coordenadas de las palabras.

    Devuelve ``None`` cuando el PDF no tiene capa de texto (no hay nada que
    reconstruir por posición) para que el pipeline use el texto del OCR.

    ``region`` limita los **movimientos** a un rectángulo (``page``, ``x0``,
    ``y0``, ``x1``, ``y1`` en puntos PDF): cuando la persona marca una zona del
    resumen, se usan las mismas columnas y la misma limpieza que en una lectura
    completa, en vez de adivinar sobre texto plano.
    """
    if not pages or not any(page.words for page in pages):
        return None

    result = ExtractedStatement(engine="layout")

    # --- encabezado: cierre, vencimiento, saldo y pago mínimo -----------
    first = pages[0]
    header_lines = _lines(first.words)
    # Etiquetas por banco: Amex usa "CIERRE ACTUAL"/"SALDO $", otros emiten
    # "Fecha de cierre"/"Total a pagar".
    header_labels = (
        (("CIERRE ACTUAL", "FECHA DE CIERRE", "CIERRE"), "close_date", "date", ("anterior", "proximo")),
        (("VENCIMIENTO ACTUAL", "VENCIMIENTO", "VTO"), "due_date", "date", ("proximo", "anterior")),
        (("SALDO $", "TOTAL A PAGAR", "TOTAL ACTUAL", "IMPORTE TOTAL"), "total", "amount", ()),
        (("PAGO MIN.$", "PAGO MINIMO", "MINIMO A PAGAR"), "minimum", "amount", ()),
    )
    for needles, key, kind, exclude in header_labels:
        line = None
        matched = ""
        for needle in needles:
            line = _find_label_line(header_lines, needle, exclude=exclude)
            if line is not None:
                matched = needle
                break
        if line is None:
            continue
        token = _value_for(line, matched, kind, header_lines)
        if token is None:
            continue
        value: Any = _parse_date(token.text) if kind == "date" else _amount_cents(token.text)
        if value is None:
            continue
        result.fields.append(
            ExtractedField(
                key,
                value,
                "date" if kind == "date" else "money",
                0.85,
                first.number,
                [token.x0, token.y0, token.x1, token.y1],
                token.text,
            )
        )

    # --- columnas de importes -------------------------------------------
    pesos_cx: float | None = None
    dolar_cx: float | None = None
    for page in pages:
        for line in _lines(page.words):
            text = _normalize(" ".join(t.text for t in line))
            if "pesos" in text and "dolares" in text:
                for token in line:
                    normalized = _normalize(token.text)
                    if "pesos" in normalized:
                        pesos_cx = token.cx
                    elif "dolares" in normalized:
                        dolar_cx = token.cx
                if pesos_cx is not None and dolar_cx is not None:
                    break
        if pesos_cx is not None and dolar_cx is not None:
            break

    movements: list[ExtractedTransaction] = []
    for page in pages:
        for line in _lines(page.words):
            if not line:
                continue
            if region is not None and not _line_in_region(line, page, region):
                continue
            normalized = _normalize(" ".join(t.text for t in line))
            if any(keyword in normalized for keyword in _SKIP_KEYWORDS):
                continue

            occurred_on = next((value for token in _phrases(line) if (value := _parse_date(token.text))), None)
            if not occurred_on:
                continue

            # Importes con su columna; se ignora el que sigue a un marcador "USD"
            # (es el original de la compra, no la columna del resumen). Se recorren
            # las frases para no tomar el año de una fecha como importe.
            amounts: list[tuple[int, _Token]] = []
            previous = ""
            for token in _phrases(line):
                if previous in _CURRENCY_MARKERS:
                    previous = _normalize(token.text)
                    continue
                cents = _amount_cents(token.text)
                if cents is not None:
                    amounts.append((cents, token))
                previous = _normalize(token.text)
            if not amounts:
                continue

            if dolar_cx is not None:
                nearest = min(amounts, key=lambda pair: abs(pair[1].cx - dolar_cx))
                currency = "USD" if abs(nearest[1].cx - dolar_cx) < abs(nearest[1].cx - (pesos_cx or 0)) else "ARS"
            else:
                currency = "USD" if any(marker in normalized for marker in _CURRENCY_MARKERS) else "ARS"

            target_cx = dolar_cx if currency == "USD" else pesos_cx
            if target_cx is not None:
                amount_cents, amount_token = min(amounts, key=lambda pair: abs(pair[1].cx - target_cx))
            else:
                amount_cents, amount_token = amounts[-1]
            if 0 <= amount_cents < 1:
                continue

            # Descripción: sin fecha, comprobante, importes ni marcas sueltas.
            description_parts: list[str] = []
            for token in _phrases(line):
                text = token.text.strip()
                if _parse_date(text) or _amount_cents(text) is not None:
                    continue
                if re.fullmatch(r"[\-_.,()$]+", text):
                    # Marcas sueltas del resumen: "_", "( )", "$".
                    continue
                if not description_parts and re.fullmatch(r"\d{3,}\*?", text):
                    # El número de comprobante ("733304*") va antes de la
                    # descripción; los del medio (RG 5617) sí son parte de ella.
                    continue
                description_parts.append(text)
            while description_parts and _normalize(description_parts[-1]) in _CURRENCY_MARKERS:
                description_parts.pop()
            description = re.sub(r"\s+", " ", " ".join(description_parts)).strip(" -·|,.(_")[:120]
            if len(description) < 3:
                continue

            movement = ExtractedTransaction(
                occurred_on=occurred_on,
                description=description,
                amount_cents=amount_cents,
                currency=currency,
                kind=_kind_for(description),
                category=guess_category(description),
                page=page.number,
                bbox=[amount_token.x0, min(t.y0 for t in line), amount_token.x1, max(t.y1 for t in line)],
                confidence=0.8,
            )
            installment = re.search(r"(?:cuota\s*)?0?(\d{1,2})\s*/\s*0?(\d{1,2})", description, re.IGNORECASE)
            if installment:
                number, total = int(installment.group(1)), int(installment.group(2))
                if 1 <= number <= total <= 60:
                    movement.kind = "installment"
                    movement.installment_number = number
                    movement.installment_total = total
            movements.append(movement)

    if not movements:
        return None

    for movement in movements:
        if movement.kind == "installment":
            result.installments.append(movement)
        elif movement.kind == "subscription":
            result.subscriptions.append(movement)
        else:
            result.transactions.append(movement)

    full_text = " ".join(str(word["text"]) for page in pages for word in page.words)
    result.fields.append(ExtractedField("currency", "ARS", "text", 0.9))
    result.fields.append(ExtractedField("brand", _guess_brand(full_text), "text", 0.7))
    result.raw_text = "\n".join(" ".join(t.text for t in line) for page in pages for line in _lines(page.words))
    return result
