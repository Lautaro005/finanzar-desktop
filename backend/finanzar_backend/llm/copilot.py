"""Copiloto local con recuperación y evidencia.

Reglas:
- Responde **solo** con datos confirmados de SQLite y fragmentos indexados en
  ChromaDB. Si no hay evidencia, dice: "No tengo datos confirmados suficientes".
- Toda respuesta incluye las fuentes usadas (ids legibles).
- Nunca recomienda inversiones ni inventa importes.
- Si el runtime del LLM no está disponible, compone una respuesta determinística
  a partir de la misma evidencia (mismo contrato de salida).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..chroma_store.store import MemoryStore
from ..core.money import format_ars
from ..db.repo import Repository
from ..finance.engine import FinanceEngine, period_of, today
from .client import LlamaClient

logger = logging.getLogger(__name__)

NO_EVIDENCE = "No tengo datos confirmados suficientes para responder eso."
OUT_OF_SCOPE = (
    "Solo puedo ayudarte con tus finanzas: balance, pagos y vencimientos, cuotas, suscripciones, "
    "ingresos y metas. Probá con «¿cuánto tengo que pagar?»."
)

# Palabras que indican que la pregunta es sobre las finanzas de la persona.
_FINANCE_HINTS = (
    "plata",
    "dinero",
    "gast",
    "compr",
    "pagu",
    "pago",
    "pag",
    "deud",
    "tarjeta",
    "banco",
    "cuenta",
    "ahorr",
    "sueldo",
    "cobr",
    "cuota",
    "suscrip",
    "saldo",
    "ingres",
    "presupuest",
    "meta",
    "dólar",
    "dolar",
    "peso",
    "factura",
    "resumen",
    "venc",
    "cierre",
    "impuest",
    "percep",
    "gasto",
    "límite",
    "limite",
    "disponible",
    "mes",
    "plata",
    "consum",
    "movimiento",
    "gasté",
    "gaste",
    "compra",
    "compré",
    "compre",
)

SYSTEM_PROMPT = (
    "Sos el copiloto financiero local de FinanzAR. Respondés en español rioplatense, breve y claro: "
    "una o dos frases, sin listas ni títulos.\n"
    "El mensaje del usuario incluye una sección EVIDENCIA con datos ya confirmados de la persona: "
    "esos datos SON reales y suficientes. Usalos para responder y no los contradigas.\n"
    "Respondé directamente la pregunta con los números de la EVIDENCIA (por ejemplo, si te "
    "preguntan cuánto tiene que pagar, decí el importe del total a pagar).\n"
    "No copies ni repitas la sección EVIDENCIA, no enumeres las fuentes ni escribas la palabra "
    "«Fuentes», y no inventes importes, fechas ni entidades que no estén ahí.\n"
    "Solo si la sección EVIDENCIA estuviera vacía respondé exactamente: "
    f"'{NO_EVIDENCE}' "
    "No das asesoramiento financiero ni recomendás inversiones."
)

# Formas en que el modelo chico se niega aunque la evidencia exista.
_REFUSAL_MARKERS = (
    "no tengo datos",
    "no tengo suficiente",
    "no tengo información",
    "no tengo informacion",
    "no hay datos",
    "no puedo responder",
    "no puedo determinar",
    "sin datos confirmados",
)

_INTENTS: dict[str, tuple[str, ...]] = {
    "payments": ("pagar", "pago", "vence", "vencimiento", "debo", "cuánto tengo que pagar", "total a pagar"),
    "installments": ("cuota", "cuotas", "planes"),
    "subscriptions": ("suscrip", "netflix", "spotify", "streaming", "recurrente"),
    "salary": ("sueldo", "salario", "cobro", "acredita"),
    "goals": ("meta", "ahorro", "objetivo", "emergencia", "fondo"),
    "monthly": ("mes pasado", "cambió", "diferencia", "comparar", "comparación"),
    "duplicates": ("repetido", "duplicado", "dos veces", "similar"),
    # "¿cuáles fueron mis consumos?" no era del alcance y el copiloto se negaba.
    "spending": ("consum", "gasté", "gaste", "mis gastos", "gastos del mes", "movimientos", "en qué gast"),
    "balance": ("balance", "disponible", "plata", "cuánto puedo gastar", "gastar"),
}


@dataclass
class Source:
    id: str
    label: str
    kind: str
    amount_cents: int | None = None
    currency: str = "ARS"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "label": self.label, "kind": self.kind}
        if self.amount_cents is not None:
            payload["amountCents"] = self.amount_cents
            payload["amount"] = format_ars(self.amount_cents, self.currency)
            payload["currency"] = self.currency
        return payload


@dataclass
class CopilotAnswer:
    answer: str
    sources: list[Source] = field(default_factory=list)
    evidence_available: bool = True
    engine: str = "deterministic"
    used_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
            "evidenceAvailable": self.evidence_available,
            "engine": self.engine,
            "usedLlm": self.used_llm,
        }


def detect_intents(question: str) -> list[str]:
    lowered = question.lower()
    found = [intent for intent, words in _INTENTS.items() if any(word in lowered for word in words)]
    return found or ["general"]


def looks_financial(question: str) -> bool:
    """¿La pregunta es sobre las finanzas de la persona?"""
    lowered = question.lower()
    if any(intent != "general" for intent in detect_intents(question)):
        return True
    return any(hint in lowered for hint in _FINANCE_HINTS)


def _model_name(raw: str) -> str:
    """Nombre legible del modelo: ``llama-server`` devuelve la ruta del .gguf."""
    if not raw:
        return "spark"
    name = Path(raw).name
    if name.lower().endswith(".gguf"):
        name = Path(name).stem
    return name or "spark"


class Copilot:
    def __init__(
        self,
        repo: Repository,
        engine: FinanceEngine,
        memory: MemoryStore,
        client: LlamaClient | None,
        user_name: str | None = None,
    ) -> None:
        self.repo = repo
        self.engine = engine
        self.memory = memory
        self.client = client
        self.user_name = (user_name or "").strip() or None

    def system_prompt(self) -> str:
        """Prompt del sistema, con el nombre de la persona cuando lo cargó."""
        if not self.user_name:
            return SYSTEM_PROMPT
        return (
            f"{SYSTEM_PROMPT}\n"
            f"La persona que te consulta se llama {self.user_name}: podés dirigirte a ella por su "
            "nombre si queda natural, sin saludar en cada respuesta."
        )

    # -- evidencia --------------------------------------------------------
    def gather_evidence(self, question: str, period: str | None = None) -> list[Source]:
        period = period or period_of(today())
        intents = detect_intents(question)
        sources: list[Source] = []

        if any(i in intents for i in ("balance", "general", "payments", "salary")):
            accounts = self.engine.account_balances()
            if accounts:
                sources.append(
                    Source(
                        "balance:total",
                        "Balance disponible consolidado",
                        "balance",
                        self.engine.consolidated_balance(),
                    )
                )
                for account in accounts:
                    sources.append(
                        Source(
                            f"account:{account['id']}",
                            f"Cuenta {account['name']}",
                            "account",
                            account["balance_cents"],
                        )
                    )
            income = self.engine.income_for_period(period)
            if income:
                sources.append(Source(f"income:{period}", f"Ingresos {period}", "income", income))

        if "payments" in intents or "general" in intents:
            pending = self.engine.pending_payments(period)
            for payment in pending:
                sources.append(
                    Source(
                        f"payment:{payment['id']}",
                        f"Vencimiento {payment['due_date']} ({payment['kind']})",
                        "payment",
                        payment["amount_cents"],
                    )
                )
            if pending:
                total = self.engine.total_to_pay(period)
                sources.append(
                    Source(
                        f"payments:{period}",
                        f"Total a pagar {period}",
                        "payments_total",
                        total["pendingCents"],
                    )
                )

        if "installments" in intents:
            for installment in self.engine.commitments()["activeInstallments"]:
                sources.append(
                    Source(
                        f"installment:{installment['id']}",
                        f"{installment['description']} cuota "
                        f"{installment['installment_number']}/{installment['installment_total']}",
                        "installment",
                        installment["amount_cents"],
                    )
                )

        if "subscriptions" in intents:
            for sub in self.repo.list_subscriptions(active_only=True):
                sources.append(
                    Source(
                        f"subscription:{sub['id']}",
                        f"Suscripción {sub['name']}",
                        "subscription",
                        sub["amount_cents"],
                    )
                )

        if "goals" in intents:
            for goal in self.repo.list_goals():
                sources.append(
                    Source(
                        f"goal:{goal['id']}",
                        f"Meta {goal['name']}: {format_ars(goal['saved_cents'])} de {format_ars(goal['target_cents'])}",
                        "goal",
                        goal["target_cents"],
                    )
                )

        if "salary" in intents or "general" in intents:
            next_credit = self.engine.next_recurring_credit()
            if next_credit:
                sources.append(
                    Source(
                        f"recurring:{next_credit['name']}",
                        f"Próxima acreditación {next_credit['date']} · {next_credit['name']}",
                        "recurring_income",
                        next_credit["amount_cents"],
                    )
                )

        if "duplicates" in intents:
            for insight in self.repo.list_insights():
                if insight["kind"] == "duplicate":
                    sources.append(Source(f"insight:{insight['id']}", insight["title"], "insight"))

        if "spending" in intents:
            summary = self.engine.spending_summary(period)
            if summary["count"]:
                sources.append(
                    Source(
                        f"spending:{period}",
                        f"Consumos {period} ({summary['count']} movimientos)",
                        "spending",
                        summary["totalCents"],
                    )
                )
                for item in summary["topCategories"]:
                    sources.append(
                        Source(
                            f"category:{item['category']}",
                            f"Categoría {item['category']}",
                            "spending_category",
                            item["amountCents"],
                        )
                    )
                for currency, amount in summary["byCurrency"].items():
                    if currency != "ARS":
                        sources.append(
                            Source(
                                f"spending:{currency}",
                                f"Consumos en {currency}",
                                "spending_currency",
                                amount,
                                currency,
                            )
                        )

        if "monthly" in intents or "general" in intents:
            for insight in self.repo.list_insights():
                if insight["kind"] == "monthly_comparison":
                    sources.append(Source(f"insight:{insight['id']}", insight["title"], "insight"))

        # Retriever semántico sobre fragmentos confirmados.
        try:
            hits = self.memory.query("statement_chunks", question, period=None, confirmed_only=True, limit=4)
            for hit in hits:
                meta = hit.get("metadata") or {}
                sources.append(
                    Source(
                        f"chunk:{hit['id']}",
                        f"Fragmento de resumen pág. {meta.get('page', '?')}",
                        "chunk",
                    )
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("retrieval semántico no disponible: %s", exc)

        return sources

    # -- respuesta --------------------------------------------------------
    def answer(self, question: str, period: str | None = None) -> CopilotAnswer:
        # Fuera de alcance: no se le pasa a la EVIDENCIA ni al modelo. Un modelo
        # chico, si le mostrás el balance, contesta cualquier cosa con el balance.
        if not looks_financial(question):
            return CopilotAnswer(answer=OUT_OF_SCOPE, sources=[], evidence_available=False, engine="scope")

        sources = self.gather_evidence(question, period)

        if sources and self.client is not None and self.client.available():
            try:
                return self._answer_with_llm(question, sources, period)
            except Exception as exc:  # pragma: no cover - runtime caído
                logger.warning("El LLM falló (%s); se usa respuesta determinística", exc)

        deterministic = self._deterministic_answer(question, sources)
        if deterministic is None:
            # No hay datos ni una respuesta clara para esa pregunta.
            return CopilotAnswer(
                answer=NO_EVIDENCE, sources=[], evidence_available=False, engine="deterministic"
            )
        return CopilotAnswer(
            answer=deterministic,
            sources=sources,
            evidence_available=True,
            engine="deterministic",
        )

    def _evidence_block(self, sources: list[Source]) -> str:
        lines = []
        for source in sources:
            amount = (
                f" = {format_ars(source.amount_cents, source.currency)}"
                if source.amount_cents is not None
                else ""
            )
            lines.append(f"[{source.id}] {source.label}{amount}")
        return "\n".join(lines)

    def _answer_with_llm(self, question: str, sources: list[Source], period: str | None) -> CopilotAnswer:
        assert self.client is not None
        messages = [
            {"role": "system", "content": self.system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Período: {period or period_of(today())}\n"
                    f"EVIDENCIA:\n{self._evidence_block(sources)}\n\n"
                    f"PREGUNTA: {question}"
                ),
            },
        ]
        result = self.client.chat(messages, temperature=0.1, max_tokens=400)
        content = (result.content or "").strip()
        # Nunca decir "sin datos" cuando hay evidencia: si el modelo se niega,
        # repite la evidencia o responde vacío, se responde con la composición
        # determinística sobre las mismas fuentes.
        if self._should_fall_back(content):
            return CopilotAnswer(
                answer=self._deterministic_answer(question, sources) or NO_EVIDENCE,
                sources=sources,
                evidence_available=True,
                engine="deterministic-after-llm",
            )
        return CopilotAnswer(
            answer=self._clean_answer(content),
            sources=sources,
            evidence_available=True,
            engine=_model_name(result.model),
            used_llm=True,
        )

    @staticmethod
    def _should_fall_back(content: str) -> bool:
        if not content or len(content) < 12:
            return True
        lowered = content.lower()
        if NO_EVIDENCE.rstrip(".").lower() in lowered:
            return True
        if any(marker in lowered for marker in _REFUSAL_MARKERS):
            return True
        # El modelo copió la EVIDENCIA en vez de responder: se detecta por la
        # cantidad de ids entre corchetes.
        return len(re.findall(r"\[[a-z_]+:", content)) >= 3

    @staticmethod
    def _clean_answer(content: str) -> str:
        """Quita markdown suelto y la lista de fuentes del texto.

        Las fuentes ya viajan aparte y el widget las muestra plegadas al final:
        si el modelo las escribe dentro de la respuesta, se ven mezcladas.
        """
        cleaned = content.strip()
        cleaned = re.sub(r"^\s*#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace("__", "")
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\n*\s*(Fuentes|Fuente|Sources?)\s*:[^\n]*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n*\s*\[[a-z_]+:[^\]]*\]\.?\s*$", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _deterministic_answer(self, question: str, sources: list[Source]) -> str | None:
        """Respuesta armada con los datos confirmados; ``None`` si no hay con qué."""
        intents = detect_intents(question)
        lines: list[str] = []
        by_kind: dict[str, list[Source]] = {}
        for source in sources:
            by_kind.setdefault(source.kind, []).append(source)

        if "balance" in by_kind:
            lines.append(f"Tu balance disponible es {format_ars(by_kind['balance'][0].amount_cents or 0)}.")
        if "payments_total" in by_kind:
            total = by_kind["payments_total"][0].amount_cents or 0
            lines.append(f"Tenés {format_ars(total)} para pagar este período.")
        if "payment" in by_kind:
            next_payment = by_kind["payment"][0]
            lines.append(
                f"El próximo vencimiento es {next_payment.label} "
                f"por {format_ars(next_payment.amount_cents or 0)}."
            )
        elif "payments" in intents:
            lines.append("No hay vencimientos pendientes en este período.")
        if "installment" in by_kind:
            total = sum(s.amount_cents or 0 for s in by_kind["installment"])
            lines.append(f"Hay {len(by_kind['installment'])} cuotas activas por {format_ars(total)}.")
        elif "installments" in intents:
            lines.append("No tenés cuotas activas registradas.")
        if "subscription" in by_kind:
            total = sum(s.amount_cents or 0 for s in by_kind["subscription"])
            lines.append(f"Tenés {len(by_kind['subscription'])} suscripciones activas por {format_ars(total)}.")
        elif "subscriptions" in intents:
            lines.append("No hay suscripciones activas registradas.")
        if "goal" in by_kind:
            lines.append(f"Tus metas: {'; '.join(s.label for s in by_kind['goal'])}.")
        if "spending" in by_kind:
            total = by_kind["spending"][0]
            lines.append(f"{total.label}: {format_ars(total.amount_cents or 0)}.")
            categories = by_kind.get("spending_category", [])
            if categories:
                detail = ", ".join(
                    f"{source.label.replace('Categoría ', '')} {format_ars(source.amount_cents or 0)}"
                    for source in categories[:3]
                )
                lines.append(f"Donde más gastaste: {detail}.")
            for source in by_kind.get("spending_currency", []):
                lines.append(f"{source.label}: {format_ars(source.amount_cents or 0, source.currency)}.")
        elif "spending" in intents:
            lines.append("No hay consumos registrados en este período.")
        if "recurring_income" in by_kind:
            lines.append(f"Próximo ingreso: {by_kind['recurring_income'][0].label}.")
        if "insight" in by_kind:
            lines.append("; ".join(s.label for s in by_kind["insight"]) + ".")
        elif "duplicates" in intents:
            lines.append("No encontré gastos repetidos.")
        if "income" in by_kind:
            lines.append(f"Ingresos confirmados del período: {format_ars(by_kind['income'][0].amount_cents or 0)}.")

        if not lines:
            return None
        # Las fuentes no van en el texto: se muestran aparte (plegadas) en el widget.
        return " ".join(lines)
