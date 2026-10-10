"""Tests de exportación XLSX."""

from __future__ import annotations

from pathlib import Path

from finanzar_backend.export.xlsx import SHEETS, build_workbook, export_xlsx, preview


def test_workbook_has_ten_required_sheets(context) -> None:
    workbook = build_workbook(context.repo, context.engine, "2026-10")
    assert workbook.sheetnames == SHEETS
    assert len(workbook.sheetnames) == 10


def test_export_writes_file(context, tmp_path: Path) -> None:
    destination = tmp_path / "export.xlsx"
    result = export_xlsx(context.repo, context.engine, "2026-10", destination)
    assert destination.exists()
    assert result["bytes"] > 0
    assert result["sheets"] == SHEETS


def test_preview_lists_sheet_counts(context) -> None:
    result = preview(context.repo, context.engine, "2026-10")
    assert result["sheets"] == SHEETS
    assert set(result["rowCounts"]) == set(SHEETS)
