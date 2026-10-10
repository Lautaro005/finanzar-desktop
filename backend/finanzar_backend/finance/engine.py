"""Motor financiero: balances, ingresos recurrentes, proyecciones y calendario.

Reglas duras:
- El dinero se calcula en centavos enteros.
- Un pago de tarjeta reduce el balance solo cuando está marcado como pagado.
- Los ingresos recurrentes se aplican una única vez por período (índice único).
- Las cuotas futuras se informan como compromisos, pero no se restan dos veces en
  la proyección: las obligaciones se restan vía ``payments``.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ..core.ids import new_id
from ..db.repo import Repository


def today() -> date:
    return date.today()


def period_of(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_bounds(period: str) -> tuple[date, date]:
    year, month = (int(part) for part in period.split("-"))
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def clamp_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


@dataclass
class Projection:
    months: int
    cutoff: str
    start_balance_cents: int
    future_income_cents: int
    future_payments_cents: int
    end_balance_cents: int
    assumptions: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "months": self.months,
            "cutoff": self.cutoff,
            "startBalanceCents": self.start_balance_cents,
            "futureIncomeCents": self.future_income_cents,
            "futurePaymentsCents": self.future_payments_cents,
            "endBalanceCents": self.end_balance_cents,
            "assumptions": self.assumptions,
            "sources": self.sources,
        }


class FinanceEngine:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # -- ingresos recurrentes --------------------------------------------
    def apply_recurring_income(self, up_to: date | None = None) -> list[dict[str, Any]]:
        """Aplica ingresos recurrentes cuyo día ya llegó y no fueron aplicados."""
        up_to = up_to or today()
        created: list[dict[str, Any]] = []
        for income in self.repo.list_recurring_income():
            if not income["active"]:
                continue
            start = date.fromisoformat(income["start_date"])
            if start > up_to:
                continue
            if income.get("end_date") and date.fromisoformat(income["end_date"]) < up_to:
                continue
            period = period_of(up_to)
            year, month = (int(p) for p in period.split("-"))
            occurrence = clamp_day(year, month, income["day_of_month"])
            if occurrence < max(start, date(year, month, 1)):
                continue
            if occurrence > up_to:
                continue
            existing = self.repo.db.query_one(
                "SELECT id FROM income_entries WHERE recurring_income_id = ? AND occurred_on = ?",
                (income["id"], occurrence.isoformat()),
            )
            if existing:
                continue
            amount = income["amount_cents"]
            inflation = income.get("inflation_pct") or 0.0
            if inflation:
                months_elapsed = (year - start.year) * 12 + (month - start.month)
                amount = round(amount * ((1 + inflation / 100.0) ** max(0, months_elapsed)))
            entry = self.repo.upsert_income_entry(
                new_id("inc"),
                {
                    "account_id": income.get("account_id"),
                    "recurring_income_id": income["id"],
                    "source": income["source"],
                    "kind": income.get("kind", "salary"),
                    "amount_cents": amount,
                    "currency": income.get("currency", "ARS"),
                    "occurred_on": occurrence.isoformat(),
                    "note": "Aplicado automáticamente",
                },
            )
            created.append(entry)
        return created

    # -- balances ---------------------------------------------------------
    def account_balances(self) -> list[dict[str, Any]]:
        accounts = self.repo.list_accounts()
        payments_paid = self.repo.db.query(
            "SELECT p.amount_cents AS amount, c.account_id AS account_id "
            "FROM payments p JOIN credit_cards c ON c.id = p.card_id "
            "WHERE p.user_id = ? AND p.status = 'paid' AND c.account_id IS NOT NULL",
            (self.repo.user_id,),
        )
        paid_by_account: dict[str, int] = {}
        for row in payments_paid:
            paid_by_account[row["account_id"]] = paid_by_account.get(row["account_id"], 0) + row["amount"]

        incomes = self.repo.list_income_entries()
        income_by_account: dict[str, int] = {}
        for entry in incomes:
            account_id = entry.get("account_id") or "__unassigned__"
            income_by_account[account_id] = income_by_account.get(account_id, 0) + entry["amount_cents"]

        result = []
        for account in accounts:
            balance = (
                account["opening_balance_cents"]
                + income_by_account.get(account["id"], 0)
                - paid_by_account.get(account["id"], 0)
            )
            result.append({**account, "balance_cents": balance})
        return result

    def consolidated_balance(self) -> int:
        """Suma de cuentas activas (no archivadas)."""
        return sum(a["balance_cents"] for a in self.account_balances())

    def income_for_period(self, period: str) -> int:
        start, end = month_bounds(period)
        rows = self.repo.db.query(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM income_entries "
            "WHERE user_id = ? AND occurred_on >= ? AND occurred_on <= ?",
            (self.repo.user_id, start.isoformat(), end.isoformat()),
        )
        return int(rows[0]["total"]) if rows else 0

    def next_recurring_credit(self, reference: date | None = None) -> dict[str, Any] | None:
        reference = reference or today()
        best: dict[str, Any] | None = None
        for income in self.repo.list_recurring_income():
            if not income["active"]:
                continue
            candidate = None
            for offset in range(0, 13):
                year = reference.year + (reference.month - 1 + offset) // 12
                month = (reference.month - 1 + offset) % 12 + 1
                day = clamp_day(year, month, income["day_of_month"])
                if day >= reference:
                    candidate = day
                    break
            if candidate and (best is None or candidate < best["date"]):
                best = {
                    "date": candidate,
                    "amount_cents": income["amount_cents"],
                    "name": income["name"],
                    "currency": income.get("currency", "ARS"),
                }
        if best is not None:
            best["date"] = best["date"].isoformat()
        return best

    # -- pagos ------------------------------------------------------------
    def pending_payments(self, period: str | None = None) -> list[dict[str, Any]]:
        payments = self.repo.list_payments(status="pending")
        if period:
            payments = [p for p in payments if p["due_date"].startswith(period)]
        return payments

    def total_to_pay(self, period: str) -> dict[str, Any]:
        rows = self.repo.db.query(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total, COUNT(*) AS count FROM payments "
            "WHERE user_id = ? AND status != 'paid' AND substr(due_date, 1, 7) = ?",
            (self.repo.user_id, period),
        )
        paid = self.repo.db.query(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM payments "
            "WHERE user_id = ? AND status = 'paid' AND substr(due_date, 1, 7) = ?",
            (self.repo.user_id, period),
        )
        return {
            "pendingCents": int(rows[0]["total"]) if rows else 0,
            "pendingCount": int(rows[0]["count"]) if rows else 0,
            "paidCents": int(paid[0]["total"]) if paid else 0,
        }

    # -- proyección -------------------------------------------------------
    def projection(self, months: int, reference: date | None = None) -> Projection:
        reference = reference or today()
        horizon = add_months(reference, months)
        start_balance = self.consolidated_balance()

        future_income = 0
        income_sources: list[dict[str, Any]] = []
        for income in self.repo.list_recurring_income():
            if not income["active"]:
                continue
            start = date.fromisoformat(income["start_date"])
            if income.get("end_date") and date.fromisoformat(income["end_date"]) < reference:
                continue
            count = 0
            for offset in range(1, months + 1):
                year = reference.year + (reference.month - 1 + offset) // 12
                month = (reference.month - 1 + offset) % 12 + 1
                day = clamp_day(year, month, income["day_of_month"])
                if day <= horizon and start <= day:
                    count += 1
            if count:
                amount = income["amount_cents"] * count
                future_income += amount
                income_sources.append(
                    {
                        "type": "recurring_income",
                        "id": income["id"],
                        "label": f"{income['name']} · {count}×",
                        "amountCents": amount,
                    }
                )

        future_payments = 0
        payment_sources: list[dict[str, Any]] = []
        for payment in self.repo.list_payments():
            if payment["status"] == "paid":
                continue
            due = date.fromisoformat(payment["due_date"])
            if reference <= due <= horizon:
                future_payments += payment["amount_cents"]
                payment_sources.append(
                    {
                        "type": "payment",
                        "id": payment["id"],
                        "label": f"Vencimiento {payment['due_date']}",
                        "amountCents": payment["amount_cents"],
                    }
                )

        end_balance = start_balance + future_income - future_payments
        return Projection(
            months=months,
            cutoff=horizon.isoformat(),
            start_balance_cents=start_balance,
            future_income_cents=future_income,
            future_payments_cents=future_payments,
            end_balance_cents=end_balance,
            assumptions=[
                "Saldo actual de cuentas activas",
                "Ingresos recurrentes activos aplicados en su día configurado",
                "Vencimientos de tarjeta pendientes por su fecha de pago",
                "Las cuotas y suscripciones no se descuentan dos veces: vienen dentro del resumen",
            ],
            sources=[*income_sources, *payment_sources],
        )

    def projections(self, reference: date | None = None) -> dict[str, Any]:
        return {str(m): self.projection(m, reference).to_dict() for m in (1, 3, 6, 12)}

    # -- compromisos ------------------------------------------------------
    def commitments(self) -> dict[str, Any]:
        installments = self.repo.list_installments()
        active = [i for i in installments if i["remaining"] > 0 or i["installment_number"] < i["installment_total"]]
        subs = self.repo.list_subscriptions(active_only=True)
        return {
            "installments": installments,
            "activeInstallments": active,
            "installmentsCents": sum(i["amount_cents"] for i in active),
            "subscriptions": subs,
            "subscriptionsCents": sum(s["amount_cents"] for s in subs),
        }

    def emergency_fund(self) -> dict[str, Any] | None:
        goals = self.repo.list_goals()
        fund = next((g for g in goals if "emergencia" in g["name"].lower()), None)
        if not fund:
            return None
        target = max(1, fund["target_cents"])
        percent = round(fund["saved_cents"] / target * 100, 1)
        return {**fund, "percent": percent, "missingCents": max(0, fund["target_cents"] - fund["saved_cents"])}

    def low_balance_alert(self, threshold_cents: int | None = None) -> dict[str, Any] | None:
        threshold = threshold_cents
        if threshold is None:
            raw = self.repo.get_setting("low_balance_threshold_cents")
            threshold = int(raw) if raw else 200_000_00
        first_month = self.projection(1)
        if first_month.end_balance_cents < threshold:
            return {
                "thresholdCents": threshold,
                "projectedCents": first_month.end_balance_cents,
                "title": "Saldo proyectado por debajo del umbral",
                "body": "El saldo estimado al cierre queda por debajo del mínimo que definiste.",
            }
        return None

    # -- calendario -------------------------------------------------------
    def build_calendar(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for payment in self.repo.list_payments():
            if payment["status"] == "paid":
                continue
            due = date.fromisoformat(payment["due_date"])
            if from_date <= due <= to_date:
                events.append(
                    {
                        "id": new_id("cal"),
                        "event_date": payment["due_date"],
                        "kind": "due",
                        "title": f"Vencimiento · {payment['kind']}",
                        "amount_cents": payment["amount_cents"],
                        "currency": payment["currency"],
                        "ref_table": "payments",
                        "ref_id": payment["id"],
                    }
                )
        for statement in self.repo.list_statements():
            if statement.get("close_date"):
                close = date.fromisoformat(statement["close_date"])
                if from_date <= close <= to_date:
                    events.append(
                        {
                            "id": new_id("cal"),
                            "event_date": statement["close_date"],
                            "kind": "close",
                            "title": "Cierre de tarjeta",
                            "amount_cents": None,
                            "currency": statement["currency"],
                            "ref_table": "statements",
                            "ref_id": statement["id"],
                        }
                    )
        for income in self.repo.list_recurring_income():
            if not income["active"]:
                continue
            cursor = from_date
            while cursor <= to_date:
                day = clamp_day(cursor.year, cursor.month, income["day_of_month"])
                if from_date <= day <= to_date:
                    events.append(
                        {
                            "id": new_id("cal"),
                            "event_date": day.isoformat(),
                            "kind": "income",
                            "title": income["name"],
                            "amount_cents": income["amount_cents"],
                            "currency": income.get("currency", "ARS"),
                            "ref_table": "recurring_income",
                            "ref_id": income["id"],
                        }
                    )
                cursor = add_months(cursor.replace(day=1), 1)
        for installment in self.repo.list_installments():
            if installment["installment_number"] >= installment["installment_total"]:
                continue
            if installment.get("first_period"):
                year, month = (int(p) for p in installment["first_period"].split("-"))
                upcoming = add_months(date(year, month, 1), installment["installment_number"])
                if from_date <= upcoming <= to_date:
                    events.append(
                        {
                            "id": new_id("cal"),
                            "event_date": upcoming.isoformat(),
                            "kind": "installment",
                            "title": f"{installment['description']} · cuota {installment['installment_number'] + 1}",
                            "amount_cents": installment["amount_cents"],
                            "currency": installment["currency"],
                            "ref_table": "installments",
                            "ref_id": installment["id"],
                        }
                    )
        for goal in self.repo.list_goals():
            if goal.get("target_date"):
                target = date.fromisoformat(goal["target_date"])
                if from_date <= target <= to_date:
                    events.append(
                        {
                            "id": new_id("cal"),
                            "event_date": goal["target_date"],
                            "kind": "goal",
                            "title": f"Meta · {goal['name']}",
                            "amount_cents": goal["target_cents"],
                            "currency": goal["currency"],
                            "ref_table": "savings_goals",
                            "ref_id": goal["id"],
                        }
                    )
        return sorted(events, key=lambda e: (e["event_date"], e["kind"]))

    def refresh_calendar(self, reference: date | None = None) -> int:
        reference = reference or today()
        events = self.build_calendar(reference - timedelta(days=90), reference + timedelta(days=400))
        return self.repo.replace_calendar_events(events)

    # -- dashboard --------------------------------------------------------
    def dashboard(self, period: str) -> dict[str, Any]:
        self.apply_recurring_income()
        start, end = month_bounds(period)
        accounts = self.account_balances()
        balances: dict[str, int] = {}
        for account in accounts:
            balances[account["currency"]] = balances.get(account["currency"], 0) + account["balance_cents"]

        statements = self.repo.list_statements()
        pending_documents = [s for s in statements if s["status"] not in {"confirmed"}]
        return {
            "period": period,
            "balance": {
                "totalCents": self.consolidated_balance(),
                "byCurrency": balances,
                "accounts": accounts,
            },
            "income": {
                "monthCents": self.income_for_period(period),
                "recurring": self.repo.list_recurring_income(),
                "nextCredit": self.next_recurring_credit(),
            },
            "payments": self.total_to_pay(period),
            "upcomingPayments": [
                p
                for p in self.pending_payments()
                if start <= date.fromisoformat(p["due_date"]) <= add_months(end, 1)
            ][:6],
            "projection": self.projection(1).to_dict(),
            "projections": self.projections(),
            "commitments": {
                "installmentsCents": self.commitments()["installmentsCents"],
                "subscriptionsCents": self.commitments()["subscriptionsCents"],
                "activeInstallments": len(self.commitments()["activeInstallments"]),
                "subscriptions": len(self.commitments()["subscriptions"]),
            },
            "emergencyFund": self.emergency_fund(),
            "lowBalanceAlert": self.low_balance_alert(),
            "documents": {
                "total": len(statements),
                "pending": len(pending_documents),
                "pendingList": [
                    {"id": s["id"], "filename": s["filename"], "status": s["status"]} for s in pending_documents
                ],
            },
            "insights": self.repo.list_insights()[:6],
            "calendar": self.repo.list_calendar(period + "-01", end.isoformat()),
        }
