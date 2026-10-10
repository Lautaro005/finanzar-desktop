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


def test_balance_includes_income_without_account(settings):
    """El sueldo y los ingresos sin cuenta asignada también mueven el balance."""
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": 0})
        ctx.repo.upsert_income_entry(
            new_id("inc"),
            {"source": "Freelance", "amount_cents": to_cents("120000"), "occurred_on": "2026-10-05"},
        )
        assert ctx.engine.consolidated_balance() == to_cents("120000")
    finally:
        ctx.db.close()


def test_deleting_recurring_income_voids_it_without_recreating(settings):
    """Borrar el sueldo aplicado lo anula: no suma ni vuelve a aparecer."""
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_recurring_income(
            new_id("rec"),
            {
                "name": "Sueldo",
                "kind": "salary",
                "amount_cents": to_cents("300000"),
                "day_of_month": 1,
                "start_date": "2026-01-01",
            },
        )
        applied = ctx.engine.apply_recurring_income(date(2026, 10, 9))
        assert len(applied) == 1
        assert ctx.engine.consolidated_balance() == to_cents("300000")

        assert ctx.repo.delete_income_entry(applied[0]["id"]) is True
        assert ctx.engine.consolidated_balance() == 0
        # No se vuelve a aplicar en el siguiente refresco ni aparece en el historial.
        assert ctx.engine.apply_recurring_income(date(2026, 10, 9)) == []
        assert ctx.repo.list_income_entries() == []
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


def test_no_low_balance_alert_without_accounts(settings):
    """Una instalación limpia no debe mostrar alertas de saldo bajo."""
    from finanzar_backend.api.deps import build_context
    from finanzar_backend.finance.insights import refresh_insights

    ctx = build_context(settings)
    try:
        assert ctx.engine.low_balance_alert() is None
        refresh_insights(ctx.engine, "2026-10")
        assert [insight for insight in ctx.repo.list_insights() if insight["kind"] == "low_balance"] == []
    finally:
        ctx.db.close()


def test_low_balance_alert_with_accounts_under_threshold(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(new_id("acc"), {"name": "Banco", "opening_balance_cents": to_cents("1000")})
        alert = ctx.engine.low_balance_alert(threshold_cents=to_cents("100000"))
        assert alert is not None
        assert alert["projectedCents"] < alert["thresholdCents"]
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


def test_balance_separates_pesos_and_dolares(settings):
    """Los saldos en dólares no se suman a los pesos: van por moneda."""
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.create_account(
            new_id("acc"), {"name": "Banco", "currency": "ARS", "opening_balance_cents": to_cents("100000")}
        )
        usd_account = ctx.repo.create_account(
            new_id("acc"), {"name": "Dólares", "currency": "USD", "opening_balance_cents": to_cents("50")}
        )
        ctx.repo.upsert_income_entry(
            new_id("inc"),
            {
                "account_id": usd_account["id"],
                "source": "Freelance USD",
                "kind": "punctual",
                "amount_cents": to_cents("25"),
                "currency": "USD",
                "occurred_on": "2026-10-02",
            },
        )
        balances = ctx.engine.balances_by_currency()
        assert balances["ARS"] == to_cents("100000")
        assert balances["USD"] == to_cents("75")
        # El consolidado es la moneda base (ARS): no mezcla dólares.
        assert ctx.engine.consolidated_balance() == to_cents("100000")
    finally:
        ctx.db.close()


def test_spending_summary_groups_by_category(settings):
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.insert_transactions(
            [
                {
                    "id": new_id("tx"),
                    "occurred_on": "2026-10-05",
                    "description": "Super La Plaza",
                    "category": "Alimentación",
                    "amount_cents": to_cents("40000"),
                    "currency": "ARS",
                    "kind": "purchase",
                    "confirmed": 1,
                },
                {
                    "id": new_id("tx"),
                    "occurred_on": "2026-10-06",
                    "description": "Farmacity",
                    "category": "Salud",
                    "amount_cents": to_cents("10000"),
                    "currency": "ARS",
                    "kind": "purchase",
                    "confirmed": 1,
                },
                {
                    "id": new_id("tx"),
                    "occurred_on": "2026-10-07",
                    "description": "Apple",
                    "category": "Suscripción",
                    "amount_cents": 199,
                    "currency": "USD",
                    "kind": "subscription",
                    "confirmed": 1,
                },
            ]
        )
        summary = ctx.engine.spending_summary("2026-10")
        assert summary["count"] == 3
        assert summary["byCurrency"]["ARS"] == to_cents("50000")
        assert summary["byCurrency"]["USD"] == 199
        assert summary["topCategories"][0]["category"] == "Alimentación"
    finally:
        ctx.db.close()


def test_legacy_income_without_account_still_counts(settings):
    """Un ingreso viejo sin cuenta (datos ya cargados) sigue sumando al balance."""
    from finanzar_backend.api.deps import build_context

    ctx = build_context(settings)
    try:
        ctx.repo.upsert_income_entry(
            new_id("inc"),
            {
                "account_id": None,
                "source": "Sueldo viejo",
                "kind": "salary",
                "amount_cents": to_cents("32000"),
                "currency": "ARS",
                "occurred_on": "2026-10-04",
            },
        )
        assert ctx.engine.consolidated_balance() == to_cents("32000")
    finally:
        ctx.db.close()
