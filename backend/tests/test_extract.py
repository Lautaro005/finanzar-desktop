"""Tests de extracción estructurada (JSON schema y heurística)."""

from __future__ import annotations

from finanzar_backend.core.money import to_cents
from finanzar_backend.ocr.extract import (
    EXTRACTION_SCHEMA,
    build_extraction_prompt,
    extract_heuristic,
    from_llm_payload,
    parse_llm_json,
)
from finanzar_backend.ocr.glm_ocr import PageText

STATEMENT_TEXT = """BANCO GALICIA - VISA
Resumen de cuenta
Periodo: 2026-10
Fecha de cierre: 28/10/2026
Vencimiento actual: 10/10/2026
Total a pagar: 218.450,00
Pago minimo: 43.690,00
Detalle de consumos
08/10/2026 Mercado La Plaza 42.860,00
04/10/2026 Streaming Max 8.990,00
03/10/2026 Cuota notebook 04/12 94.700,00
02/10/2026 Farmacity 16.420,00
"""


def _pages() -> list[PageText]:
    return [PageText(number=1, text=STATEMENT_TEXT, engine="native-pymupdf")]


def test_heuristic_extracts_header_fields() -> None:
    extracted = extract_heuristic(_pages())
    fields = extracted.field_map()
    assert fields["total"].value == to_cents("218450")
    assert fields["minimum"].value == to_cents("43690")
    assert fields["due_date"].value == "2026-10-10"
    assert fields["close_date"].value == "2026-10-28"
    assert fields["brand"].value == "visa"
    assert fields["currency"].value == "ARS"


def test_heuristic_extracts_movements_and_installments() -> None:
    extracted = extract_heuristic(_pages())
    descriptions = {tx.description for tx in extracted.transactions}
    assert any("Mercado La Plaza" in d for d in descriptions)
    assert any("Farmacity" in d for d in descriptions)
    marketplace = next(tx for tx in extracted.transactions if "Mercado" in tx.description)
    assert marketplace.amount_cents == to_cents("42860")
    assert marketplace.category == "Alimentación"

    assert len(extracted.installments) == 1
    installment = extracted.installments[0]
    assert installment.installment_number == 4
    assert installment.installment_total == 12
    assert installment.kind == "installment"

    assert len(extracted.subscriptions) == 1
    assert "Streaming" in extracted.subscriptions[0].description


def test_heuristic_keeps_confidence_and_page() -> None:
    extracted = extract_heuristic(_pages())
    for tx in extracted.transactions:
        assert tx.confidence is not None
        assert tx.page == 1


def test_schema_is_strict_and_has_all_sections() -> None:
    assert EXTRACTION_SCHEMA["additionalProperties"] is False
    properties = EXTRACTION_SCHEMA["properties"]
    for key in ("card", "period", "close_date", "due_date", "total", "minimum", "movements", "installments", "subscriptions", "charges"):
        assert key in properties
    assert "required" in EXTRACTION_SCHEMA


def test_prompt_includes_schema_and_text() -> None:
    prompt = build_extraction_prompt(STATEMENT_TEXT)
    assert "SCHEMA" in prompt
    assert "No inventes importes" in prompt
    assert "Mercado La Plaza" in prompt


def test_parse_llm_json_handles_code_fences() -> None:
    payload = '```json\n{"total": 100}\n```'
    assert parse_llm_json(payload) == {"total": 100}
    assert parse_llm_json("sin json") is None


def test_from_llm_payload_builds_structure() -> None:
    payload = {
        "card": "Visa Galicia",
        "brand": "visa",
        "period": "2026-10",
        "close_date": "2026-10-28",
        "due_date": "2026-10-10",
        "total": 218450.0,
        "minimum": 43690.0,
        "currency": "ARS",
        "movements": [
            {"date": "2026-10-08", "description": "Mercado La Plaza", "amount": 42860.0},
            {
                "date": "2026-10-03",
                "description": "Cuota notebook",
                "amount": 94700.0,
                "installment_number": 4,
                "installment_total": 12,
            },
        ],
        "installments": [],
        "subscriptions": [],
        "charges": [],
    }
    extracted = from_llm_payload(payload, _pages())
    assert extracted.engine == "llm"
    fields = extracted.field_map()
    assert fields["due_date"].value == "2026-10-10"
    assert len(extracted.transactions) == 1
    assert len(extracted.installments) == 1
