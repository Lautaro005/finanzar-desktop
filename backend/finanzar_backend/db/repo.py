"""Repositorios de acceso a datos. Toda la escritura pasa por acá."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from .. import LOCAL_USER_ID
from ..core.ids import new_id
from .sqlite import Database, utcnow


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(zip(row.keys(), tuple(row), strict=False))


class Repository:
    def __init__(self, db: Database, user_id: str = LOCAL_USER_ID) -> None:
        self.db = db
        self.user_id = user_id

    # -- auditoría --------------------------------------------------------
    def audit(
        self,
        action: str,
        *,
        entity: str | None = None,
        entity_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO audit_events (id, user_id, at, actor, action, entity, entity_id, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("audit"),
                self.user_id,
                utcnow(),
                "local",
                action,
                entity,
                entity_id,
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )

    # -- settings ---------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self.db.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.db.upsert_setting(key, value)

    def all_settings(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self.db.query("SELECT key, value FROM app_settings")}

    # -- accounts ---------------------------------------------------------
    def create_account(self, account_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        self.db.execute(
            "INSERT INTO accounts (id, user_id, name, kind, currency, opening_balance_cents, "
            "institution, masked_number, close_day, due_day, archived, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                account_id,
                self.user_id,
                data["name"],
                data.get("kind", "bank"),
                data.get("currency", "ARS"),
                data.get("opening_balance_cents", 0),
                data.get("institution"),
                data.get("masked_number"),
                data.get("close_day"),
                data.get("due_day"),
                1 if data.get("archived") else 0,
                data.get("notes"),
                now,
                now,
            ),
        )
        self.audit("account.create", entity="accounts", entity_id=account_id, details={"name": data["name"]})
        return self.get_account(account_id)  # type: ignore[return-value]

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        row = self.db.query_one(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, self.user_id)
        )
        return _row_to_dict(row) if row else None

    def list_accounts(self, include_archived: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM accounts WHERE user_id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY created_at"
        return [_row_to_dict(r) for r in self.db.query(sql, (self.user_id,))]

    def update_account(self, account_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "name",
            "kind",
            "currency",
            "opening_balance_cents",
            "institution",
            "masked_number",
            "close_day",
            "due_day",
            "archived",
            "notes",
        }
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return self.get_account(account_id)
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values: list[Any] = []
        for key, value in fields.items():
            values.append(1 if key == "archived" and value else (0 if key == "archived" else value))
        values.extend([utcnow(), account_id, self.user_id])
        self.db.execute(
            f"UPDATE accounts SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
            values,
        )
        self.audit("account.update", entity="accounts", entity_id=account_id, details=fields)
        return self.get_account(account_id)

    # -- credit cards -----------------------------------------------------
    def create_card(self, card_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        self.db.execute(
            "INSERT INTO credit_cards (id, user_id, account_id, name, brand, last4, currency, "
            "close_day, due_day, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card_id,
                self.user_id,
                data.get("account_id"),
                data["name"],
                data.get("brand", "other"),
                data.get("last4"),
                data.get("currency", "ARS"),
                data.get("close_day"),
                data.get("due_day"),
                1 if data.get("active", True) else 0,
                now,
                now,
            ),
        )
        return self.get_card(card_id)  # type: ignore[return-value]

    def get_card(self, card_id: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM credit_cards WHERE id = ?", (card_id,))
        return _row_to_dict(row) if row else None

    def list_cards(self) -> list[dict[str, Any]]:
        return [
            _row_to_dict(r)
            for r in self.db.query(
                "SELECT * FROM credit_cards WHERE user_id = ? ORDER BY created_at", (self.user_id,)
            )
        ]

    # -- recurring income -------------------------------------------------
    def create_recurring_income(self, income_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        self.db.execute(
            "INSERT INTO recurring_income (id, user_id, name, source, kind, amount_cents, currency, "
            "account_id, day_of_month, start_date, end_date, active, repeat_rule, inflation_pct, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                income_id,
                self.user_id,
                data["name"],
                data.get("source", data["name"]),
                data.get("kind", "salary"),
                data["amount_cents"],
                data.get("currency", "ARS"),
                data.get("account_id"),
                data.get("day_of_month", 1),
                data["start_date"],
                data.get("end_date"),
                1 if data.get("active", True) else 0,
                data.get("repeat_rule", "monthly"),
                data.get("inflation_pct", 0.0),
                data.get("notes"),
                now,
                now,
            ),
        )
        self.audit("recurring_income.create", entity="recurring_income", entity_id=income_id)
        return self.get_recurring_income(income_id)  # type: ignore[return-value]

    def get_recurring_income(self, income_id: str) -> dict[str, Any] | None:
        row = self.db.query_one(
            "SELECT * FROM recurring_income WHERE id = ? AND user_id = ?", (income_id, self.user_id)
        )
        return _row_to_dict(row) if row else None

    def list_recurring_income(self) -> list[dict[str, Any]]:
        return [
            _row_to_dict(r)
            for r in self.db.query(
                "SELECT * FROM recurring_income WHERE user_id = ? ORDER BY created_at", (self.user_id,)
            )
        ]

    def update_recurring_income(self, income_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "name",
            "source",
            "kind",
            "amount_cents",
            "currency",
            "account_id",
            "day_of_month",
            "start_date",
            "end_date",
            "active",
            "repeat_rule",
            "inflation_pct",
            "notes",
        }
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return self.get_recurring_income(income_id)
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = [1 if k == "active" and v else (0 if k == "active" else v) for k, v in fields.items()]
        values.extend([utcnow(), income_id, self.user_id])
        self.db.execute(
            f"UPDATE recurring_income SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
            values,
        )
        self.audit("recurring_income.update", entity="recurring_income", entity_id=income_id, details=fields)
        return self.get_recurring_income(income_id)

    # -- income entries ---------------------------------------------------
    def upsert_income_entry(self, entry_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO income_entries (id, user_id, account_id, recurring_income_id, source, kind, "
            "amount_cents, currency, occurred_on, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(recurring_income_id, occurred_on) DO UPDATE SET "
            "amount_cents=excluded.amount_cents, account_id=excluded.account_id, note=excluded.note",
            (
                entry_id,
                self.user_id,
                data.get("account_id"),
                data.get("recurring_income_id"),
                data["source"],
                data.get("kind", "punctual"),
                data["amount_cents"],
                data.get("currency", "ARS"),
                data["occurred_on"],
                data.get("note"),
                utcnow(),
            ),
        )
        self.audit("income.create", entity="income_entries", entity_id=entry_id)
        return {"id": entry_id, **data}

    def list_income_entries(self, *, from_date: str | None = None, to_date: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM income_entries WHERE user_id = ?"
        params: list[Any] = [self.user_id]
        if from_date:
            sql += " AND occurred_on >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND occurred_on <= ?"
            params.append(to_date)
        sql += " ORDER BY occurred_on DESC"
        return [_row_to_dict(r) for r in self.db.query(sql, params)]

    # -- statements / documents -------------------------------------------
    def create_statement(self, statement_id: str, data: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        self.db.execute(
            "INSERT INTO statements (id, user_id, card_id, checksum, filename, stored_path, period, "
            "close_date, due_date, total_cents, minimum_cents, currency, status, pages, source, "
            "imported_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                statement_id,
                self.user_id,
                data.get("card_id"),
                data["checksum"],
                data["filename"],
                data["stored_path"],
                data.get("period"),
                data.get("close_date"),
                data.get("due_date"),
                data.get("total_cents"),
                data.get("minimum_cents"),
                data.get("currency", "ARS"),
                data.get("status", "imported"),
                data.get("pages", 0),
                data.get("source", "pdf"),
                now,
                now,
            ),
        )
        self.audit(
            "document.import",
            entity="statements",
            entity_id=statement_id,
            details={"filename": data["filename"]},
        )
        return self.get_statement(statement_id)  # type: ignore[return-value]

    def get_statement(self, statement_id: str) -> dict[str, Any] | None:
        row = self.db.query_one(
            "SELECT * FROM statements WHERE id = ? AND user_id = ?", (statement_id, self.user_id)
        )
        return _row_to_dict(row) if row else None

    def get_statement_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM statements WHERE checksum = ?", (checksum,))
        return _row_to_dict(row) if row else None

    def list_statements(self) -> list[dict[str, Any]]:
        return [
            _row_to_dict(r)
            for r in self.db.query(
                "SELECT * FROM statements WHERE user_id = ? ORDER BY imported_at DESC", (self.user_id,)
            )
        ]

    def update_statement(self, statement_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "card_id",
            "period",
            "close_date",
            "due_date",
            "total_cents",
            "minimum_cents",
            "currency",
            "status",
            "pages",
            "confirmed_at",
        }
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return self.get_statement(statement_id)
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = [*fields.values(), utcnow(), statement_id, self.user_id]
        self.db.execute(
            f"UPDATE statements SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
            values,
        )
        return self.get_statement(statement_id)

    # -- statement fields -------------------------------------------------
    def upsert_statement_field(self, field_id: str, statement_id: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO statement_fields (id, statement_id, field_key, field_value, value_type, confidence, "
            "source_page, source_bbox, evidence_text, status, confirmed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(statement_id, field_key) DO UPDATE SET field_value=excluded.field_value, "
            "value_type=excluded.value_type, confidence=excluded.confidence, source_page=excluded.source_page, "
            "source_bbox=excluded.source_bbox, evidence_text=excluded.evidence_text, status=excluded.status, "
            "confirmed_at=excluded.confirmed_at, updated_at=excluded.updated_at",
            (
                field_id,
                statement_id,
                data["field_key"],
                data.get("field_value"),
                data.get("value_type", "text"),
                data.get("confidence"),
                data.get("source_page"),
                json.dumps(data["source_bbox"]) if data.get("source_bbox") else None,
                data.get("evidence_text"),
                data.get("status", "pending"),
                data.get("confirmed_at"),
                utcnow(),
            ),
        )

    def list_statement_fields(self, statement_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM statement_fields WHERE statement_id = ? ORDER BY field_key", (statement_id,)
        )
        result = []
        for row in rows:
            item = _row_to_dict(row)
            if item.get("source_bbox"):
                item["source_bbox"] = json.loads(item["source_bbox"])
            result.append(item)
        return result

    def patch_statement_field(
        self, statement_id: str, field_key: str, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        allowed = {"field_value", "status", "confidence", "confirmed_at"}
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            return None
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = [*fields.values(), utcnow(), statement_id, field_key]
        self.db.execute(
            f"UPDATE statement_fields SET {assignments}, updated_at = ? "
            "WHERE statement_id = ? AND field_key = ?",
            values,
        )
        self.audit("document.field_patch", entity="statement_fields", entity_id=f"{statement_id}:{field_key}")
        rows = self.list_statement_fields(statement_id)
        return next((f for f in rows if f["field_key"] == field_key), None)

    # -- transactions -----------------------------------------------------
    def insert_transactions(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.db.transaction() as conn:
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO transactions (id, user_id, statement_id, card_id, occurred_on, "
                    "description, normalized_description, category, amount_cents, currency, "
                    "foreign_amount_cents, foreign_currency, installment_number, installment_total, kind, "
                    "confirmed, source_page, source_bbox, confidence, content_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"],
                        self.user_id,
                        row.get("statement_id"),
                        row.get("card_id"),
                        row["occurred_on"],
                        row["description"],
                        row.get("normalized_description"),
                        row.get("category"),
                        row["amount_cents"],
                        row.get("currency", "ARS"),
                        row.get("foreign_amount_cents"),
                        row.get("foreign_currency"),
                        row.get("installment_number"),
                        row.get("installment_total"),
                        row.get("kind", "purchase"),
                        1 if row.get("confirmed") else 0,
                        row.get("source_page"),
                        json.dumps(row["source_bbox"]) if row.get("source_bbox") else None,
                        row.get("confidence"),
                        row.get("content_hash"),
                        utcnow(),
                    ),
                )
                count += 1
        return count

    def list_transactions(
        self,
        *,
        period: str | None = None,
        card_id: str | None = None,
        kind: str | None = None,
        confirmed: bool | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM transactions WHERE user_id = ?"
        params: list[Any] = [self.user_id]
        if period:
            sql += " AND substr(occurred_on, 1, 7) = ?"
            params.append(period)
        if card_id:
            sql += " AND card_id = ?"
            params.append(card_id)
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if confirmed is not None:
            sql += " AND confirmed = ?"
            params.append(1 if confirmed else 0)
        sql += " ORDER BY occurred_on DESC, description"
        return [_row_to_dict(r) for r in self.db.query(sql, params)]

    def update_transaction(self, tx_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"category", "description", "kind", "confirmed", "occurred_on", "amount_cents"}
        fields = {k: v for k, v in patch.items() if k in allowed}
        if not fields:
            row = self.db.query_one("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (tx_id, self.user_id))
            return _row_to_dict(row) if row else None
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = [
            1 if k == "confirmed" and v else (0 if k == "confirmed" else v) for k, v in fields.items()
        ]
        values.extend([tx_id, self.user_id])
        self.db.execute(f"UPDATE transactions SET {assignments} WHERE id = ? AND user_id = ?", values)
        self.audit("transaction.update", entity="transactions", entity_id=tx_id, details=list(fields))
        row = self.db.query_one("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (tx_id, self.user_id))
        return _row_to_dict(row) if row else None

    # -- installments -----------------------------------------------------
    def insert_installments(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.db.transaction() as conn:
            for row in rows:
                conn.execute(
                    "INSERT INTO installments (id, user_id, card_id, statement_id, transaction_id, "
                    "description, installment_number, installment_total, amount_cents, currency, "
                    "first_period, remaining, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["id"],
                        self.user_id,
                        row.get("card_id"),
                        row.get("statement_id"),
                        row.get("transaction_id"),
                        row["description"],
                        row["installment_number"],
                        row["installment_total"],
                        row["amount_cents"],
                        row.get("currency", "ARS"),
                        row.get("first_period"),
                        row.get("remaining", 0),
                        utcnow(),
                    ),
                )
                count += 1
        return count

    def list_installments(self, card_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM installments WHERE user_id = ?"
        params: list[Any] = [self.user_id]
        if card_id:
            sql += " AND card_id = ?"
            params.append(card_id)
        sql += " ORDER BY first_period DESC"
        return [_row_to_dict(r) for r in self.db.query(sql, params)]

    # -- subscriptions ----------------------------------------------------
    def upsert_subscription(self, sub_id: str, data: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO subscriptions (id, user_id, card_id, name, amount_cents, currency, periodicity, "
            "last_seen_period, occurrences, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET amount_cents=excluded.amount_cents, "
            "last_seen_period=excluded.last_seen_period, occurrences=excluded.occurrences, "
            "active=excluded.active, updated_at=excluded.updated_at",
            (
                sub_id,
                self.user_id,
                data.get("card_id"),
                data["name"],
                data["amount_cents"],
                data.get("currency", "ARS"),
                data.get("periodicity", "monthly"),
                data.get("last_seen_period"),
                data.get("occurrences", 1),
                1 if data.get("active", True) else 0,
                utcnow(),
                utcnow(),
            ),
        )

    def list_subscriptions(self, active_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM subscriptions WHERE user_id = ?"
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY name"
        return [_row_to_dict(r) for r in self.db.query(sql, (self.user_id,))]

    # -- payments ---------------------------------------------------------
    def upsert_payment(self, payment_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO payments (id, user_id, card_id, statement_id, due_date, amount_cents, currency, "
            "kind, status, paid_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(statement_id, kind) DO UPDATE SET amount_cents=excluded.amount_cents, "
            "due_date=excluded.due_date, kind=excluded.kind, status=excluded.status, paid_at=excluded.paid_at",
            (
                payment_id,
                self.user_id,
                data.get("card_id"),
                data.get("statement_id"),
                data["due_date"],
                data["amount_cents"],
                data.get("currency", "ARS"),
                data.get("kind", "total"),
                data.get("status", "pending"),
                data.get("paid_at"),
                utcnow(),
            ),
        )
        self.audit("payment.upsert", entity="payments", entity_id=payment_id, details={"status": data.get("status")})
        row = self.db.query_one(
            "SELECT * FROM payments WHERE statement_id = ? AND kind = ?",
            (data.get("statement_id"), data.get("kind", "total")),
        )
        return _row_to_dict(row) if row else {"id": payment_id, **data}

    def list_payments(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM payments WHERE user_id = ?"
        params: list[Any] = [self.user_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY due_date"
        return [_row_to_dict(r) for r in self.db.query(sql, params)]

    # -- calendar ---------------------------------------------------------
    def replace_calendar_events(self, events: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM calendar_events WHERE user_id = ?", (self.user_id,))
            for event in events:
                conn.execute(
                    "INSERT INTO calendar_events (id, user_id, event_date, kind, title, amount_cents, "
                    "currency, ref_table, ref_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event["id"],
                        self.user_id,
                        event["event_date"],
                        event["kind"],
                        event["title"],
                        event.get("amount_cents"),
                        event.get("currency"),
                        event.get("ref_table"),
                        event.get("ref_id"),
                        utcnow(),
                    ),
                )
                count += 1
        return count

    def list_calendar(self, from_date: str | None = None, to_date: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM calendar_events WHERE user_id = ?"
        params: list[Any] = [self.user_id]
        if from_date:
            sql += " AND event_date >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND event_date <= ?"
            params.append(to_date)
        sql += " ORDER BY event_date, kind"
        return [_row_to_dict(r) for r in self.db.query(sql, params)]

    # -- goals ------------------------------------------------------------
    def upsert_goal(self, goal_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO savings_goals (id, user_id, name, target_cents, saved_cents, currency, account_id, "
            "salary_percent, target_date, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, target_cents=excluded.target_cents, "
            "saved_cents=excluded.saved_cents, account_id=excluded.account_id, "
            "salary_percent=excluded.salary_percent, target_date=excluded.target_date, "
            "active=excluded.active, updated_at=excluded.updated_at",
            (
                goal_id,
                self.user_id,
                data["name"],
                data["target_cents"],
                data.get("saved_cents", 0),
                data.get("currency", "ARS"),
                data.get("account_id"),
                data.get("salary_percent"),
                data.get("target_date"),
                1 if data.get("active", True) else 0,
                utcnow(),
                utcnow(),
            ),
        )
        row = self.db.query_one("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        return _row_to_dict(row) if row else {"id": goal_id, **data}

    def list_goals(self) -> list[dict[str, Any]]:
        return [
            _row_to_dict(r)
            for r in self.db.query(
                "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY created_at", (self.user_id,)
            )
        ]

    # -- insights ---------------------------------------------------------
    def replace_insights(self, insights: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM insights WHERE user_id = ?", (self.user_id,))
            for item in insights:
                conn.execute(
                    "INSERT INTO insights (id, user_id, kind, period, title, body, severity, query, "
                    "evidence_json, confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item["id"],
                        self.user_id,
                        item["kind"],
                        item.get("period"),
                        item["title"],
                        item["body"],
                        item.get("severity", "info"),
                        item.get("query"),
                        json.dumps(item.get("evidence", []), ensure_ascii=False),
                        item.get("confirmed", 1),
                        utcnow(),
                    ),
                )
                count += 1
        return count

    def list_insights(self) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM insights WHERE user_id = ? ORDER BY created_at DESC", (self.user_id,)
        )
        result = []
        for row in rows:
            item = _row_to_dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
            result.append(item)
        return result

    # -- copilot history --------------------------------------------------
    def add_copilot_message(
        self, message_id: str, role: str, content: str, sources: list[dict[str, Any]]
    ) -> None:
        self.db.execute(
            "INSERT INTO copilot_messages (id, user_id, role, content, sources_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message_id, self.user_id, role, content, json.dumps(sources, ensure_ascii=False), utcnow()),
        )

    def list_copilot_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM copilot_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.user_id, limit),
        )
        result = []
        for row in reversed(rows):
            item = _row_to_dict(row)
            item["sources"] = json.loads(item.pop("sources_json") or "[]")
            result.append(item)
        return result

    def clear_copilot_messages(self) -> None:
        self.db.execute("DELETE FROM copilot_messages WHERE user_id = ?", (self.user_id,))
