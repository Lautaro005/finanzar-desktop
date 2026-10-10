"""Tests de seguridad de rutas y de la base de datos."""

from __future__ import annotations

from pathlib import Path

import pytest

from finanzar_backend.api.deps import resolve_document_path
from finanzar_backend.core.errors import PathNotAllowedError
from finanzar_backend.db.repo import Repository
from finanzar_backend.db.sqlite import Database


def test_traversal_is_blocked(settings) -> None:
    with pytest.raises(PathNotAllowedError):
        resolve_document_path(settings, "../../etc/passwd")
    with pytest.raises(PathNotAllowedError):
        resolve_document_path(settings, "/etc/passwd")


def test_path_inside_documents_is_allowed(settings) -> None:
    resolved = resolve_document_path(settings, "resumen.pdf")
    assert resolved == (settings.documents_dir / "resumen.pdf").resolve()


def test_migrations_apply_once(settings) -> None:
    db = Database(settings.db_path)
    try:
        applied = db.migrate()
        assert "0001_initial" in applied
        assert db.migrate() == []
        assert db.schema_version() == "0001_initial"
        tables = {
            row["name"]
            for row in db.query("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for expected in (
            "app_settings",
            "accounts",
            "recurring_income",
            "income_entries",
            "credit_cards",
            "statements",
            "statement_fields",
            "transactions",
            "installments",
            "subscriptions",
            "payments",
            "calendar_events",
            "savings_goals",
            "insights",
            "audit_events",
            "model_installations",
        ):
            assert expected in tables
    finally:
        db.close()


def test_repository_audit_and_settings(settings) -> None:
    db = Database(settings.db_path)
    db.migrate()
    try:
        repo = Repository(db)
        repo.set_setting("low_balance_threshold_cents", "500000")
        assert repo.get_setting("low_balance_threshold_cents") == "500000"
        repo.audit("test.action", entity="tests", entity_id="1")
        events = db.query("SELECT action FROM audit_events WHERE user_id = 'local'")
        assert any(row["action"] == "test.action" for row in events)
    finally:
        db.close()


def test_documents_dir_is_created(settings) -> None:
    assert isinstance(settings.documents_dir, Path)
    assert settings.documents_dir.exists()
    assert settings.models_dir.exists()
