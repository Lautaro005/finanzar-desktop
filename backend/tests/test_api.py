"""Tests de integración de la API local (envelope, documentos, OCR, export)."""

from __future__ import annotations

from pathlib import Path

from conftest import make_statement_pdf


def _data(response):
    payload = response.json()
    assert payload["ok"] is True, payload
    assert payload["error"] is None
    assert payload["request_id"]
    return payload["data"]


def _error(response):
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"]
    assert payload["error"]["message"]
    return payload["error"]


def test_health_envelope(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = _data(response)
    assert data["status"] == "ok"
    assert data["schemaVersion"].startswith("0001")


def test_bootstrap_lists_models_and_runtime(client) -> None:
    data = _data(client.get("/api/bootstrap"))
    ids = {model["id"] for model in data["models"]}
    assert {"glm-ocr", "spark-x2.5-1.7b"}.issubset(ids)
    assert data["runtime"]["build"] == "b10828"


def test_account_crud(client) -> None:
    created = _data(
        client.post("/api/accounts", json={"name": "Cuenta sueldo", "kind": "bank", "openingBalance": "1000,00"})
    )["account"]
    assert created["opening_balance_cents"] == 100000

    listed = _data(client.get("/api/accounts"))["accounts"]
    assert len(listed) == 1

    patched = _data(client.patch(f"/api/accounts/{created['id']}", json={"name": "Renombrada"}))["account"]
    assert patched["name"] == "Renombrada"

    missing = client.patch("/api/accounts/nope", json={"name": "x"})
    assert missing.status_code == 404
    assert _error(missing)["code"] == "not_found"


def test_income_updates_balance(client) -> None:
    account = _data(client.post("/api/accounts", json={"name": "Banco"}))["account"]
    data = _data(
        client.post("/api/incomes", json={"amount": "5000,00", "source": "Freelance", "accountId": account["id"]})
    )
    assert data["balanceCents"] == 500000


def test_income_without_account_still_updates_balance(client) -> None:
    """El sueldo no trae cuenta: tiene que sumar igual al balance disponible."""
    data = _data(client.post("/api/incomes", json={"amount": "32000,00", "source": "Sueldo"}))
    assert data["balanceCents"] == 3_200_000


def test_income_edit_and_delete(client) -> None:
    created = _data(
        client.post("/api/incomes", json={"amountCents": 150000, "source": "Freelance", "occurredOn": "2026-10-05"})
    )
    entry_id = created["entry"]["id"]

    patched = _data(client.patch(f"/api/incomes/{entry_id}", json={"amountCents": 200000, "source": "Freelance II"}))
    assert patched["entry"]["amount_cents"] == 200000
    assert patched["entry"]["source"] == "Freelance II"
    assert patched["balanceCents"] == 200000

    deleted = _data(client.delete(f"/api/incomes/{entry_id}"))
    assert deleted["deleted"] is True
    assert deleted["balanceCents"] == 0
    remaining = _data(client.get("/api/incomes"))["entries"]
    assert all(entry["id"] != entry_id for entry in remaining)


def test_recurring_salary_is_applied(client) -> None:
    account = _data(client.post("/api/accounts", json={"name": "Banco"}))["account"]
    data = _data(
        client.post(
            "/api/incomes/recurring",
            json={
                "name": "Sueldo",
                "amount": "1000,00",
                "accountId": account["id"],
                "dayOfMonth": 1,
                "startDate": "2020-01-01",
            },
        )
    )
    assert data["balanceCents"] >= 100000
    dashboard = _data(client.get("/api/dashboard"))
    assert dashboard["income"]["monthCents"] >= 100000
    assert dashboard["projection"]["months"] == 1


def test_document_import_ocr_review_confirm_and_export(client, tmp_path: Path) -> None:
    pdf = make_statement_pdf(tmp_path / "resumen.pdf")
    content = pdf.read_bytes()

    with pdf.open("rb") as handle:
        imported = _data(
            client.post(
                "/api/documents/import",
                files={"file": ("resumen.pdf", handle, "application/pdf")},
            )
        )
    statement = imported["document"]
    assert statement["status"] == "imported"

    duplicate = client.post(
        "/api/documents/import",
        files={"file": ("resumen.pdf", content, "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert _error(duplicate)["code"] == "duplicate_document"

    ocr = _data(client.post(f"/api/documents/{statement['id']}/ocr", params={"prefer": "native"}))
    assert ocr["fields"] >= 3
    assert ocr["transactions"] >= 2

    review = _data(client.get(f"/api/documents/{statement['id']}/review"))
    keys = {field["field_key"] for field in review["fields"]}
    assert {"total", "minimum", "due_date"}.issubset(keys)
    assert review["transactions"]

    patched = _data(
        client.patch(
            f"/api/documents/{statement['id']}/fields",
            json={"fields": [{"fieldKey": "total", "value": "218450"}]},
        )
    )
    assert patched["fields"][0]["status"] == "edited"

    confirmed = _data(client.post(f"/api/documents/{statement['id']}/confirm"))
    assert confirmed["statement"]["status"] == "confirmed"
    assert confirmed["indexedChunks"] >= 1

    exported = _data(client.post("/api/export/xlsx", json={}))
    assert len(exported["sheets"]) == 10
    assert Path(exported["path"]).exists()

    preview = _data(client.get("/api/export/preview"))
    assert preview["sheets"] == exported["sheets"]


def test_transactions_and_calendar(client) -> None:
    _data(
        client.post(
            "/api/transactions",
            json={"occurredOn": "2026-10-05", "description": "Café", "amount": "1200,50", "category": "Gastos"},
        )
    )
    transactions = _data(client.get("/api/transactions", params={"month": "2026-10"}))["transactions"]
    assert transactions
    calendar = _data(client.get("/api/calendar", params={"from": "2026-10-01", "to": "2026-10-31"}))
    assert calendar["from"] == "2026-10-01"


def test_insights_endpoint(client) -> None:
    data = _data(client.get("/api/insights"))
    assert isinstance(data["insights"], list)


def test_update_check_requires_consent_field(client) -> None:
    data = _data(client.post("/api/app/update-check"))
    assert data["requiresConsent"] is True
    install = _data(client.post("/api/app/update-install"))
    assert install["requiresConsent"] is True


def test_models_status_endpoint(client) -> None:
    data = _data(client.get("/api/models/status"))
    assert data["models"]
    assert data["runtime"]["id"] == "llama-server"


def test_jobs_endpoint(client) -> None:
    data = _data(client.get("/api/jobs"))
    assert "jobs" in data
