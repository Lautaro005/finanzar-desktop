"""Workbook XLSX con las hojas financieras de FinanzAR.

Hojas: Resumen mensual, Cuentas, Ingresos, Movimientos, Cuotas, Suscripciones,
Tarjetas, Calendario, Insights y Metadatos de exportación. Incluye formato de
moneda, fechas, freeze panes y autofiltro.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..core.money import cents_to_str
from ..db.repo import Repository
from ..db.sqlite import utcnow
from ..finance.engine import FinanceEngine

SHEETS = [
    "Resumen mensual",
    "Cuentas",
    "Ingresos",
    "Movimientos",
    "Cuotas",
    "Suscripciones",
    "Tarjetas",
    "Calendario",
    "Insights",
    "Metadatos de exportación",
]

MONEY_FORMAT = '"AR$" #,##0.00'
DATE_FORMAT = "yyyy-mm-dd"
HEADER_FILL = PatternFill("solid", fgColor="D9F2E6")
HEADER_FONT = Font(bold=True, color="0B3D2E")
MONEY_COLUMNS = {
    "Total",
    "Mínimo",
    "Saldo",
    "Importe",
    "Importe ARS",
    "Importe USD",
    "Objetivo",
    "Ahorrado",
    "Monto",
    "Saldo estimado",
    "Ingresos",
    "Pagos",
}


def _write_header(ws: Worksheet, headers: list[str]) -> None:
    ws.append(headers)
    for index, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=index)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"


def _autosize(ws: Worksheet) -> None:
    for column_cells in ws.columns:
        longest = max((len(str(cell.value)) if cell.value is not None else 0) for cell in column_cells)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(48, max(12, longest + 2))


def _apply_money_format(ws: Worksheet, headers: list[str]) -> None:
    for index, header in enumerate(headers, start=1):
        if header in MONEY_COLUMNS:
            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=index).number_format = MONEY_FORMAT


def _cents(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(cents_to_str(int(value)))
    except Exception:
        return None


def build_workbook(repo: Repository, engine: FinanceEngine, period: str) -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)

    # 1. Resumen mensual
    ws = workbook.create_sheet("Resumen mensual")
    _write_header(ws, ["Métrica", "Valor", "Unidad"])
    income = engine.income_for_period(period)
    total = engine.total_to_pay(period)
    projection = engine.projection(1)
    rows = [
        ("Período", period, "texto"),
        ("Balance disponible", _cents(engine.consolidated_balance()), "moneda"),
        ("Ingresos del mes", _cents(income), "moneda"),
        ("Total a pagar", _cents(total["pendingCents"]), "moneda"),
        ("Pagos realizados", _cents(total["paidCents"]), "moneda"),
        ("Saldo proyectado (1 mes)", _cents(projection.end_balance_cents), "moneda"),
        ("Fecha de corte de la proyección", projection.cutoff, "fecha"),
        ("Cuotas activas", _cents(engine.commitments()["installmentsCents"]), "moneda"),
        ("Suscripciones activas", _cents(engine.commitments()["subscriptionsCents"]), "moneda"),
    ]
    for label, value, _unit in rows:
        ws.append([label, value, _unit])
    for row in range(2, ws.max_row + 1):
        if ws.cell(row=row, column=3).value == "moneda":
            ws.cell(row=row, column=2).number_format = MONEY_FORMAT
    _autosize(ws)

    # 2. Cuentas
    ws = workbook.create_sheet("Cuentas")
    _write_header(ws, ["Cuenta", "Tipo", "Moneda", "Saldo", "Institución", "Archivada"])
    for account in engine.account_balances():
        ws.append(
            [
                account["name"],
                account["kind"],
                account["currency"],
                _cents(account["balance_cents"]),
                account.get("institution"),
                "sí" if account["archived"] else "no",
            ]
        )
    _apply_money_format(ws, ["Saldo"])
    _autosize(ws)

    # 3. Ingresos
    ws = workbook.create_sheet("Ingresos")
    _write_header(ws, ["Fecha", "Origen", "Tipo", "Importe", "Moneda", "Recurrente"])
    for entry in repo.list_income_entries():
        ws.append(
            [
                entry["occurred_on"],
                entry["source"],
                entry["kind"],
                _cents(entry["amount_cents"]),
                entry["currency"],
                "sí" if entry.get("recurring_income_id") else "no",
            ]
        )
    _apply_money_format(ws, ["Importe"])
    _autosize(ws)

    # 4. Movimientos
    ws = workbook.create_sheet("Movimientos")
    _write_header(ws, ["Fecha", "Descripción", "Categoría", "Tipo", "Importe", "Moneda", "Confirmado", "Página"])
    for tx in repo.list_transactions():
        ws.append(
            [
                tx["occurred_on"],
                tx["description"],
                tx.get("category"),
                tx["kind"],
                _cents(tx["amount_cents"]),
                tx["currency"],
                "sí" if tx["confirmed"] else "no",
                tx.get("source_page"),
            ]
        )
    _apply_money_format(ws, ["Importe"])
    _autosize(ws)

    # 5. Cuotas
    ws = workbook.create_sheet("Cuotas")
    _write_header(ws, ["Descripción", "Cuota", "Total cuotas", "Importe", "Restantes", "Primer período"])
    for installment in repo.list_installments():
        ws.append(
            [
                installment["description"],
                installment["installment_number"],
                installment["installment_total"],
                _cents(installment["amount_cents"]),
                installment["remaining"],
                installment.get("first_period"),
            ]
        )
    _apply_money_format(ws, ["Importe"])
    _autosize(ws)

    # 6. Suscripciones
    ws = workbook.create_sheet("Suscripciones")
    _write_header(ws, ["Nombre", "Importe", "Moneda", "Periodicidad", "Último período", "Activa"])
    for sub in repo.list_subscriptions():
        ws.append(
            [
                sub["name"],
                _cents(sub["amount_cents"]),
                sub["currency"],
                sub["periodicity"],
                sub.get("last_seen_period"),
                "sí" if sub["active"] else "no",
            ]
        )
    _apply_money_format(ws, ["Importe"])
    _autosize(ws)

    # 7. Tarjetas
    ws = workbook.create_sheet("Tarjetas")
    _write_header(ws, ["Tarjeta", "Marca", "Últimos 4", "Cierre", "Vencimiento", "Moneda", "Activa"])
    for card in repo.list_cards():
        ws.append(
            [
                card["name"],
                card["brand"],
                card.get("last4"),
                card.get("close_day"),
                card.get("due_day"),
                card["currency"],
                "sí" if card["active"] else "no",
            ]
        )
    _autosize(ws)

    # 8. Calendario
    ws = workbook.create_sheet("Calendario")
    _write_header(ws, ["Fecha", "Tipo", "Título", "Importe", "Moneda"])
    for event in repo.list_calendar():
        ws.append(
            [
                event["event_date"],
                event["kind"],
                event["title"],
                _cents(event.get("amount_cents")),
                event.get("currency"),
            ]
        )
    _apply_money_format(ws, ["Importe"])
    _autosize(ws)

    # 9. Insights
    ws = workbook.create_sheet("Insights")
    _write_header(ws, ["Título", "Detalle", "Severidad", "Período", "Consulta", "Evidencia"])
    for insight in repo.list_insights():
        evidence = "; ".join(
            f"{item.get('label')}: {item.get('amountCents', item.get('text', ''))}" for item in insight["evidence"]
        )
        ws.append(
            [
                insight["title"],
                insight["body"],
                insight["severity"],
                insight.get("period"),
                insight.get("query"),
                evidence,
            ]
        )
    _autosize(ws)

    # 10. Metadatos de exportación
    ws = workbook.create_sheet("Metadatos de exportación")
    _write_header(ws, ["Clave", "Valor"])
    metadata = [
        ("Aplicación", "FinanzAR Desktop"),
        ("Exportado", utcnow()),
        ("Período", period),
        ("Moneda principal", "ARS"),
        ("Motor de cálculos", "SQLite + motor financiero local"),
        ("Nota", "Los importes están en pesos argentinos salvo que se indique otra moneda."),
        ("Privacidad", "Generado localmente; no se envió ningún dato a la nube."),
    ]
    for key, value in metadata:
        ws.append([key, value])
    _autosize(ws)

    return workbook


def export_xlsx(repo: Repository, engine: FinanceEngine, period: str, destination: Path) -> dict[str, Any]:
    workbook = build_workbook(repo, engine, period)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(destination))
    return {
        "path": str(destination),
        "bytes": destination.stat().st_size,
        "sheets": SHEETS,
        "period": period,
    }


def preview(repo: Repository, engine: FinanceEngine, period: str) -> dict[str, Any]:
    counts = {
        "Resumen mensual": 9,
        "Cuentas": len(repo.list_accounts(include_archived=True)),
        "Ingresos": len(repo.list_income_entries()),
        "Movimientos": len(repo.list_transactions()),
        "Cuotas": len(repo.list_installments()),
        "Suscripciones": len(repo.list_subscriptions()),
        "Tarjetas": len(repo.list_cards()),
        "Calendario": len(repo.list_calendar()),
        "Insights": len(repo.list_insights()),
        "Metadatos de exportación": 7,
    }
    return {"sheets": SHEETS, "rowCounts": counts, "period": period}
