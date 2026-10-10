"""Tests del copiloto: sin evidencia lo dice; con evidencia cita fuentes."""

from __future__ import annotations

from datetime import date

from finanzar_backend.core.ids import new_id
from finanzar_backend.core.money import to_cents
from finanzar_backend.llm.copilot import NO_EVIDENCE, OUT_OF_SCOPE, Copilot, detect_intents, looks_financial


def test_finance_scope_detection() -> None:
    assert looks_financial("¿cuánto tengo que pagar?")
    assert looks_financial("¿cuánto gasté en el super?")
    assert not looks_financial("cuanto es 2+2?")
    assert not looks_financial("contame un chiste")


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
    assert "balance:total" in {source.id for source in answer.sources}
    assert "AR$" in answer.answer
    # Las fuentes van aparte, no mezcladas dentro del texto de la respuesta.
    assert "Fuentes" not in answer.answer
    assert "[" not in answer.answer
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
    assert "100.000,00" in answer.answer
    assert answer.used_llm is False


class _RefusingWithOtherWordsClient(_RefusingClient):
    """Se niega con otras palabras: el modelo chico no repite el texto exacto."""

    def chat(self, *args, **kwargs):
        from finanzar_backend.llm.client import ChatResult

        return ChatResult(
            content="No tengo datos confirmados suficientes para responder esa pregunta.",
            model="/models/spark/Spark-X2.5-1.7B-Q4_K_M.gguf",
        )


class _EchoingEvidenceClient(_RefusingClient):
    """Devuelve la EVIDENCIA copiada en vez de responder."""

    def chat(self, *args, **kwargs):
        from finanzar_backend.llm.client import ChatResult

        return ChatResult(
            content=(
                "[balance:total] Balance disponible consolidado = AR$ 100.000,00\n"
                "[account:acc_1] Cuenta Banco = AR$ 100.000,00\n"
                "[income:2026-10] Ingresos 2026-10 = AR$ 0,00"
            ),
            model="/models/spark/Spark-X2.5-1.7B-Q4_K_M.gguf",
        )


def test_copilot_falls_back_when_refusal_uses_other_words(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
    copilot = Copilot(context.repo, context.engine, context.memory, _RefusingWithOtherWordsClient())  # type: ignore[arg-type]
    answer = copilot.answer("¿cuánto tengo disponible?")
    assert answer.used_llm is False
    assert answer.engine == "deterministic-after-llm"
    assert "100.000,00" in answer.answer


def test_copilot_falls_back_when_model_echoes_evidence(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
    copilot = Copilot(context.repo, context.engine, context.memory, _EchoingEvidenceClient())  # type: ignore[arg-type]
    answer = copilot.answer("¿cuánto tengo disponible?")
    assert answer.used_llm is False
    assert "[balance:total]" not in answer.answer


def test_copilot_refuses_off_topic_questions(context) -> None:
    """Una pregunta que no es de finanzas no se responde con el balance."""
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
    copilot = Copilot(context.repo, context.engine, context.memory, _RefusingClient())  # type: ignore[arg-type]
    answer = copilot.answer("cuanto es 2+2?")
    assert answer.answer == OUT_OF_SCOPE
    assert answer.sources == []
    assert answer.evidence_available is False
    assert answer.used_llm is False
    # No filtra datos financieros en una pregunta que no es de finanzas.
    assert "AR$" not in answer.answer


def test_copilot_installments_without_data_says_so(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
    copilot = Copilot(context.repo, context.engine, context.memory, None)
    answer = copilot.answer("¿qué cuotas siguen?")
    assert "cuotas" in answer.answer.lower()
    assert "no tenés cuotas activas" in answer.answer.lower()


def test_copilot_strips_sources_written_by_the_model(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})

    class _ChattyClient(_RefusingClient):
        def chat(self, *args, **kwargs):
            from finanzar_backend.llm.client import ChatResult

            return ChatResult(
                content="Tu balance es AR$ 100.000,00.\nFuentes: [balance:total, account:acc_1].",
                model="fake-model",
            )

    copilot = Copilot(context.repo, context.engine, context.memory, _ChattyClient())  # type: ignore[arg-type]
    answer = copilot.answer("¿cuánto tengo disponible?")
    assert answer.used_llm is True
    assert "Fuentes" not in answer.answer
    assert "[balance:total" not in answer.answer
    assert answer.sources


def test_copilot_reports_a_readable_model_name(context) -> None:
    context.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})

    class _AnsweringClient(_RefusingClient):
        def chat(self, *args, **kwargs):
            from finanzar_backend.llm.client import ChatResult

            return ChatResult(
                content="Tenés AR$ 100.000,00 disponibles [balance:total].",
                model="/models/spark/Spark-X2.5-1.7B-Q4_K_M.gguf",
            )

    copilot = Copilot(context.repo, context.engine, context.memory, _AnsweringClient())  # type: ignore[arg-type]
    answer = copilot.answer("¿cuánto tengo disponible?")
    assert answer.used_llm is True
    assert answer.engine == "Spark-X2.5-1.7B-Q4_K_M"
