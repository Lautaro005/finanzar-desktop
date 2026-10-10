"""Tests del copiloto: sin evidencia lo dice; con evidencia cita fuentes."""

from __future__ import annotations

from datetime import date

from finanzar_backend.core.ids import new_id
from finanzar_backend.core.money import to_cents
from finanzar_backend.llm.copilot import NO_EVIDENCE, Copilot, detect_intents


def test_intent_detection() -> None:
    assert "payments" in detect_intents("¿qué vence esta semana?")
    assert "installments" in detect_intents("¿qué cuotas siguen?")
    assert "subscriptions" in detect_intents("¿qué suscripciones se repiten?")
    assert detect_intents("hola") == ["general"]


def test_copilot_says_no_evidence_when_empty(context) -> None:
    copilot = Copilot(context.repo, context.engine, context.memory, None)
    answer = copilot.answer("¿cuánto puedo gastar este mes?")
    assert answer.answer == NO_EVIDENCE
    assert answer.evidence_available is False
    assert answer.sources == []


def test_copilot_answers_with_sources_when_data_exists(context) -> None:
    account = context.repo.create_account(
        new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("500000")}
    )
    context.repo.create_recurring_income(
        new_id("rec"),
        {
            "name": "Sueldo",
            "kind": "salary",
            "amount_cents": to_cents("300000"),
            "account_id": account["id"],
            "day_of_month": 1,
            "start_date": "2026-01-01",
        },
    )
    context.engine.apply_recurring_income(date(2026, 10, 9))

    copilot = Copilot(context.repo, context.engine, context.memory, None)
    answer = copilot.answer("¿cuánto tengo disponible y cuándo cobro el sueldo?")
    assert answer.evidence_available is True
    assert answer.sources
    assert "Fuentes" in answer.answer
    assert "balance:total" in {source.id for source in answer.sources}
    # Nunca recomienda inversiones.
    assert "invert" not in answer.answer.lower()


class _RefusingClient:
    """Cliente falso que siempre devuelve el texto de 'sin datos'."""

    def __init__(self) -> None:
        self.base_url = "http://127.0.0.1:0"

    def available(self) -> bool:
        return True

    def chat(self, *args, **kwargs):
        from finanzar_backend.llm.client import ChatResult

        return ChatResult(content=NO_EVIDENCE, model="fake-model")


def test_copilot_never_says_no_evidence_when_sources_exist(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
    copilot = Copilot(context.repo, context.engine, context.memory, _RefusingClient())  # type: ignore[arg-type]
    answer = copilot.answer("¿cuánto tengo disponible?")
    assert answer.evidence_available is True
    assert answer.sources
    assert answer.answer != NO_EVIDENCE
    assert "Fuentes" in answer.answer
    assert answer.used_llm is False
