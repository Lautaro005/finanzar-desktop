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

SYSTEM_PROMPT = (
    "Sos el copiloto financiero local de FinanzAR. Respondés en español rioplatense, breve y claro: "
    "una o dos frases, sin listas ni títulos.\n"
    "El mensaje del usuario incluye una sección EVIDENCIA con datos ya confirmados de la persona: "
    "esos datos SON reales y suficientes. Usalos para responder y no los contradigas.\n"
    "Respondé directamente la pregunta con los números de la EVIDENCIA (por ejemplo, si te "
    "preguntan cuánto tiene que pagar, decí el importe del total a pagar).\n"
    "No copies ni repitas la sección EVIDENCIA, no enumeres las fuentes una por una y no inventes "
    "importes, fechas ni entidades que no estén ahí.\n"
    "Solo si la sección EVIDENCIA estuviera vacía respondé exactamente: "
    f"'{NO_EVIDENCE}' "
    "No das asesoramiento financiero ni recomendás inversiones.\n"
    "Terminá mencionando las fuentes usadas con su id entre corchetes, por ejemplo [balance:total]."
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
    "balance": ("balance", "disponible", "plata", "cuánto puedo gastar", "gastar"),
}


@dataclass
class Source:
    id: str
    label: str
    kind: str
    amount_cents: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "label": self.label, "kind": self.kind}
        if self.amount_cents is not None:
            payload["amountCents"] = self.amount_cents
            payload["amount"] = format_ars(self.amount_cents)
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
    ) -> None:
        self.repo = repo
        self.engine = engine
        self.memory = memory
        self.client = client

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
        sources = self.gather_evidence(question, period)
        if not sources:
            return CopilotAnswer(answer=NO_EVIDENCE, sources=[], evidence_available=False, engine="deterministic")

        if self.client is not None and self.client.available():
            try:
                return self._answer_with_llm(question, sources, period)
            except Exception as exc:  # pragma: no cover - runtime caído
                logger.warning("El LLM falló (%s); se usa respuesta determinística", exc)

        return CopilotAnswer(
            answer=self._deterministic_answer(question, sources),
            sources=sources,
            evidence_available=True,
            engine="deterministic",
        )

    def _evidence_block(self, sources: list[Source]) -> str:
        lines = []
        for source in sources:
            amount = f" = {format_ars(source.amount_cents)}" if source.amount_cents is not None else ""
            lines.append(f"[{source.id}] {source.label}{amount}")
        return "\n".join(lines)

    def _answer_with_llm(self, question: str, sources: list[Source], period: str | None) -> CopilotAnswer:
        assert self.client is not None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
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
                answer=self._deterministic_answer(question, sources),
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
        """Quita markdown suelto para que el widget muestre texto plano prolijo."""
        cleaned = re.sub(r"^\s*#{1,6}\s*", "", content, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace("__", "")
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _deterministic_answer(self, question: str, sources: list[Source]) -> str:
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
        if "installment" in by_kind:
            total = sum(s.amount_cents or 0 for s in by_kind["installment"])
            lines.append(f"Hay {len(by_kind['installment'])} cuotas activas por {format_ars(total)}.")
        if "subscription" in by_kind:
            total = sum(s.amount_cents or 0 for s in by_kind["subscription"])
            lines.append(f"Tenés {len(by_kind['subscription'])} suscripciones activas por {format_ars(total)}.")
        if "goal" in by_kind:
            lines.append(f"Tus metas: {'; '.join(s.label for s in by_kind['goal'])}.")
        if "recurring_income" in by_kind:
            lines.append(f"Próximo ingreso: {by_kind['recurring_income'][0].label}.")
        if "insight" in by_kind:
            lines.append("; ".join(s.label for s in by_kind["insight"]) + ".")
        if "income" in by_kind:
            lines.append(f"Ingresos confirmados del período: {format_ars(by_kind['income'][0].amount_cents or 0)}.")

        if not lines:
            lines.append("Estos son los datos confirmados que tengo disponibles.")

        used_ids = ", ".join(s.id for s in sources[:6])
        lines.append(f"Fuentes: [{used_ids}].")
        _ = intents
        return " ".join(lines)
