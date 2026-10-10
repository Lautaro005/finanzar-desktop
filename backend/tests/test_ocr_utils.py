"""Tests de robustez del OCR (decodificación y deduplicación).

No requieren torch: solo ejercitan funciones puras del pipeline.
"""

from __future__ import annotations

from finanzar_backend.ocr.extract import ExtractedTransaction
from finanzar_backend.ocr.glm_ocr import GlmOcrEngine
from finanzar_backend.ocr.pipeline import _dedupe_transactions


def _tx(description: str, amount: int = 4286000, day: str = "2026-10-08") -> ExtractedTransaction:
    return ExtractedTransaction(occurred_on=day, description=description, amount_cents=amount)


def test_dedupe_collapses_same_movement_with_ocr_noise() -> None:
    items = [
        _tx("Cuota notebook", 9470000, "2026-10-03"),
        _tx("Cuota notebook /", 9470000, "2026-10-03"),
        _tx("cuota  notebook", 9470000, "2026-10-03"),
    ]
    deduped = _dedupe_transactions(items)
    assert len(deduped) == 1
    # La descripción queda sin puntuación colgante.
    assert deduped[0].description == "Cuota notebook"


def test_dedupe_preserves_distinct_descriptions() -> None:
    items = [
        _tx("Cuota notebook 04/12", 9470000, "2026-10-03"),
        _tx("Cuota notebook 05/12", 9470000, "2026-10-03"),
    ]
    assert len(_dedupe_transactions(items)) == 2


def test_dedupe_keeps_distinct_movements() -> None:
    items = [
        _tx("Mercado La Plaza", 4286000, "2026-10-08"),
        _tx("Streaming Max", 899000, "2026-10-04"),
        _tx("Mercado La Plaza", 4286000, "2026-10-09"),
    ]
    deduped = _dedupe_transactions(items)
    assert len(deduped) == 3


def test_glm_dedupe_lines_removes_repeats() -> None:
    text = "Total a pagar: 218.450,00\nMercado La Plaza 42.860,00\nMercado La Plaza 42.860,00\nFarmacity"
    cleaned = GlmOcrEngine._dedupe_lines(text)
    assert cleaned.splitlines() == [
        "Total a pagar: 218.450,00",
        "Mercado La Plaza 42.860,00",
        "Farmacity",
    ]


def test_glm_dedupe_lines_drops_blank_lines() -> None:
    cleaned = GlmOcrEngine._dedupe_lines("uno\n\n\n   \ndos")
    assert cleaned == "uno\ndos"
