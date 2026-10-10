"""Tests del motor financiero: ingresos recurrentes, balance y proyección."""

from __future__ import annotations

from datetime import date

from finanzar_backend.core.ids import new_id
from finanzar_backend.core.money import to_cents


def test_recurring_income_applied_once(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        account = ctx.repo.create_account(new_id("acc"), {"name": "Sueldo", "opening_balance_cents": 0})
        ctx.repo.create_recurring_income(
            new_id("rec"),
            {
                "name": "Sueldo",
                "kind": "salary",
                "amount_cents": to_cents("950000"),
                "account_id": account["id"],
                "day_of_month": 1,
                "start_date": "2026-01-01",
            },
        )
        first = ctx.engine.apply_recurring_income(date(2026, 10, 9))
        assert len(first) == 1
        second = ctx.engine.apply_recurring_income(date(2026, 10, 9))
        assert second == []
        balance = ctx.engine.consolidated_balance()
        assert balance == to_cents("950000")
    finally:
        ctx.db.close()


def test_balance_reflects_paid_payment_only(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        account = ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("1000000")})
        card = ctx.repo.create_card(new_id("card"), {"name": "Visa", "brand": "visa", "account_id": account["id"]})
        statement = ctx.repo.create_statement(
            new_id("doc"),
            {
                "filename": "x.pdf",
                "checksum": "c1",
                "stored_path": "/tmp/x.pdf",
                "status": "confirmed",
                "total_cents": to_cents("200000"),
            },
        )
        payment = ctx.repo.upsert_payment(
            new_id("pay"),
            {
                "card_id": card["id"],
                "statement_id": statement["id"],
                "due_date": "2026-10-10",
                "amount_cents": to_cents("200000"),
                "kind": "total",
                "status": "pending",
            },
        )
        assert ctx.engine.consolidated_balance() == to_cents("1000000")
        ctx.repo.upsert_payment(payment["id"], {**payment, "status": "paid"})
        assert ctx.engine.consolidated_balance() == to_cents("800000")
    finally:
        ctx.db.close()


def test_projection_does_not_double_count_installments(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("100000")})
        card = ctx.repo.create_card(new_id("card"), {"name": "Visa", "brand": "visa"})
        statement = ctx.repo.create_statement(
            new_id("doc"),
            {"filename": "x.pdf", "checksum": "c2", "stored_path": "/tmp/x.pdf", "status": "confirmed"},
        )
        ctx.repo.insert_installments(
            [
                {
                    "id": new_id("ins"),
                    "card_id": card["id"],
                    "statement_id": statement["id"],
                    "description": "Notebook",
                    "installment_number": 4,
                    "installment_total": 12,
                    "amount_cents": to_cents("50000"),
                    "first_period": "2026-10",
                    "remaining": 8,
                }
            ]
        )
        ctx.repo.upsert_payment(
            new_id("pay"),
            {
                "card_id": card["id"],
                "statement_id": statement["id"],
                "due_date": "2026-11-10",
                "amount_cents": to_cents("50000"),
                "kind": "total",
                "status": "pending",
            },
        )
        projection = ctx.engine.projection(1, date(2026, 10, 15))
        # Solo se resta el pago, no además la cuota.
        assert projection.future_payments_cents == to_cents("50000")
        assert projection.end_balance_cents == to_cents("100000") - to_cents("50000")
        assert any("no se descuentan dos veces" in assumption for assumption in projection.assumptions)
    finally:
        ctx.db.close()


def test_projection_includes_future_recurring_income(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": 0})
        ctx.repo.create_recurring_income(
            new_id("rec"),
            {
                "name": "Sueldo",
                "kind": "salary",
                "amount_cents": to_cents("100000"),
                "day_of_month": 1,
                "start_date": "2026-01-01",
            },
        )
        projection = ctx.engine.projection(3, date(2026, 10, 15))
        assert projection.future_income_cents == to_cents("300000")
        assert projection.end_balance_cents == to_cents("300000")
        assert projection.cutoff == "2027-01-15"
    finally:
        ctx.db.close()


def test_calendar_includes_income_and_due_dates(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": 0})
        ctx.repo.create_recurring_income(
            new_id("rec"),
            {
                "name": "Sueldo",
                "kind": "salary",
                "amount_cents": to_cents("100000"),
                "day_of_month": 5,
                "start_date": "2026-01-01",
            },
        )
        events = ctx.engine.build_calendar(date(2026, 10, 1), date(2026, 10, 31))
        kinds = {event["kind"] for event in events}
        assert "income" in kinds
    finally:
        ctx.db.close()


def test_emergency_fund_percent(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.upsert_goal(
            new_id("goal"),
            {"name": "Fondo de emergencia", "target_cents": to_cents("2000000"), "saved_cents": to_cents("500000")},
        )
        fund = ctx.engine.emergency_fund()
        assert fund is not None
        assert fund["percent"] == 25.0
        assert fund["missingCents"] == to_cents("1500000")
    finally:
        ctx.db.close()
