"""Datos demo opcionales (nunca se cargan solos en producción).

Se habilitan solo si ``FINANZAR_ALLOW_SEED=1``. Sirven para que la app tenga algo
que mostrar en un arranque de desarrollo, sin tocar datos reales.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..core.ids import new_id
from ..core.money import to_cents
from ..db.repo import Repository
from ..finance.engine import FinanceEngine, period_of, today
from ..finance.insights import refresh_insights


def seed_demo(repo: Repository, engine: FinanceEngine, *, reference: date | None = None) -> dict[str, int]:
    reference = reference or today()
    period = period_of(reference)

    if repo.list_accounts():
        return {"accounts": 0, "note": "ya hay datos; seed omitido"}

    salary_account = repo.create_account(
        new_id("acc"),
        {
            "name": "Cuenta sueldo",
            "kind": "bank",
            "institution": "Banco Galicia",
            "masked_number": "**** 4821",
            "opening_balance_cents": to_cents("1280000"),
        },
    )
    wallet = repo.create_account(
        new_id("acc"),
        {"name": "Billetera diaria", "kind": "wallet", "opening_balance_cents": to_cents("42800")},
    )
    fund = repo.create_account(
        new_id("acc"),
        {"name": "Fondo de emergencia", "kind": "savings", "opening_balance_cents": to_cents("420000")},
    )

    card_visa = repo.create_card(
        new_id("card"),
        {"name": "Visa Galicia", "brand": "visa", "last4": "4821", "close_day": 28, "due_day": 10},
    )
    card_master = repo.create_card(
        new_id("card"),
        {"name": "Mastercard Naranja", "brand": "master", "last4": "9012", "close_day": 3, "due_day": 15},
    )

    repo.create_recurring_income(
        new_id("rec"),
        {
            "name": "Sueldo",
            "source": "Sueldo",
            "kind": "salary",
            "amount_cents": to_cents("950000"),
            "account_id": salary_account["id"],
            "day_of_month": 1,
            "start_date": (reference - timedelta(days=120)).replace(day=1).isoformat(),
        },
    )

    repo.upsert_goal(
        new_id("goal"),
        {
            "name": "Fondo de emergencia",
            "target_cents": to_cents("2000000"),
            "saved_cents": to_cents("420000"),
            "account_id": fund["id"],
            "salary_percent": 10.0,
        },
    )

    # Resumen confirmado con movimientos, cuotas y suscripciones.
    statement = repo.create_statement(
        new_id("doc"),
        {
            "filename": "visa-galicia-octubre.pdf",
            "checksum": "demo-checksum-visa-oct",
            "stored_path": str(repo.db.path.parent / "documents" / "demo-visa.pdf"),
            "period": period,
            "close_date": f"{period}-28",
            "due_date": f"{period}-10",
            "total_cents": to_cents("218450"),
            "minimum_cents": to_cents("43690"),
            "currency": "ARS",
            "status": "confirmed",
            "pages": 2,
            "confirmed_at": reference.isoformat(),
        },
    )
    repo.insert_transactions(
        [
            {
                "id": new_id("tx"),
                "statement_id": statement["id"],
                "card_id": card_visa["id"],
                "occurred_on": f"{period}-08",
                "description": "Mercado La Plaza",
                "category": "Alimentación",
                "amount_cents": to_cents("42860"),
                "confirmed": True,
                "content_hash": "demo-tx-1",
            },
            {
                "id": new_id("tx"),
                "statement_id": statement["id"],
                "card_id": card_visa["id"],
                "occurred_on": f"{period}-04",
                "description": "Streaming Max",
                "category": "Suscripción",
                "amount_cents": to_cents("8990"),
                "kind": "subscription",
                "confirmed": True,
                "content_hash": "demo-tx-2",
            },
            {
                "id": new_id("tx"),
                "statement_id": statement["id"],
                "card_id": card_master["id"],
                "occurred_on": f"{period}-03",
                "description": "Cuota notebook",
                "category": "Tecnología",
                "amount_cents": to_cents("94700"),
                "kind": "installment",
                "installment_number": 4,
                "installment_total": 12,
                "confirmed": True,
                "content_hash": "demo-tx-3",
            },
        ]
    )
    repo.insert_installments(
        [
            {
                "id": new_id("ins"),
                "card_id": card_master["id"],
                "statement_id": statement["id"],
                "description": "Cuota notebook",
                "installment_number": 4,
                "installment_total": 12,
                "amount_cents": to_cents("94700"),
                "first_period": period,
                "remaining": 8,
            }
        ]
    )
    repo.upsert_subscription(
        new_id("sub"),
        {
            "name": "Streaming Max",
            "amount_cents": to_cents("8990"),
            "card_id": card_visa["id"],
            "last_seen_period": period,
        },
    )
    repo.upsert_payment(
        new_id("pay"),
        {
            "card_id": card_visa["id"],
            "statement_id": statement["id"],
            "due_date": f"{period}-10",
            "amount_cents": to_cents("218450"),
            "kind": "total",
            "status": "pending",
        },
    )

    engine.apply_recurring_income(reference)
    engine.refresh_calendar(reference)
    refresh_insights(engine, period)
    return {
        "accounts": len(repo.list_accounts()),
        "cards": len(repo.list_cards()),
        "transactions": len(repo.list_transactions()),
        "wallet": wallet["id"],
    }
