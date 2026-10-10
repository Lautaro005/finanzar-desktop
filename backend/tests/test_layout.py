"""Tests del extractor por layout: separa la columna de pesos de la de dólares."""

from __future__ import annotations

from pathlib import Path

from finanzar_backend.ocr import pdf as pdf_mod
from finanzar_backend.ocr.layout import parse_layout


def make_two_column_statement_pdf(path: Path) -> Path:
    """Resumen tipo American Express con columnas PESOS y DOLARES.

    Se escribe con fuente monoespaciada y columnas fijas para que cada
    movimiento quede en **una sola línea** con la fecha a la izquierda y los
    importes alineados en su columna, como en el resumen real.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    char_width = 9 * 0.6  # Courier a 9pt

    def line(fields: list[tuple[int, str]]) -> str:
        chars = [" "] * 100
        for start, text in fields:
            for offset, character in enumerate(text):
                if 0 <= start + offset < len(chars):
                    chars[start + offset] = character
        return "".join(chars).rstrip()

    def put_row(y: float, fields: list[tuple[int, str]]) -> None:
        page.insert_text((72, y), line(fields), fontsize=9, fontname="cour")

    def right_aligned(text: str, end_col: int) -> tuple[int, str]:
        return (end_col - len(text), text)

    put_row(70, [(0, "American Express")])
    put_row(100, [(0, "CIERRE ACTUAL: 01 Oct 26")])
    # Fila de etiquetas y fila de valores, alineadas por columna.
    put_row(130, [(0, "VENCIMIENTO"), (30, "SALDO $"), (40, "SALDO U$S"), (50, "PAGO MIN.$")])
    put_row(145, [(0, "09 Oct 26"), right_aligned("57.999,53", 36), right_aligned("28,98", 46),
                  right_aligned("20.130,00", 58)])
    # Encabezado de la tabla de consumos y las dos columnas de importes.
    put_row(180, [(0, "FECHA COMPROBANTE DETALLE DE TRANSACCION"), right_aligned("PESOS", 70),
                  right_aligned("DOLARES", 92)])
    put_row(200, [(0, "03.09.26"), (10, "MERPAGO*CAMILAPIROYANSKY"), right_aligned("3.209,70", 70)])
    put_row(215, [(0, "29.08.26"), (10, "APPLE.COM/BILL   MVWTV4   USD   1,99"),
                  right_aligned("1,99", 92)])
    put_row(230, [(0, "04.09.26"), (10, "DEV.IMP. RG 5617 30%"), right_aligned("9.084,00-", 70)])
    put_row(245, [(0, "01.10.26"), (10, "DB.RG 5617 30%"), right_aligned("13.188,79", 70)])
    _ = char_width
    doc.save(str(path))
    doc.close()
    return path


def test_layout_separates_pesos_and_dolares(tmp_path: Path) -> None:
    pdf = make_two_column_statement_pdf(tmp_path / "resumen.pdf")
    result = parse_layout(pdf_mod.words_pages(pdf))
    assert result is not None

    fields = {field.key: field.value for field in result.fields}
    assert fields["close_date"] == "2026-10-01"
    assert fields["due_date"] == "2026-10-09"
    assert fields["total"] == 5_799_953
    assert fields["minimum"] == 2_013_000
    assert fields["currency"] == "ARS"
    assert fields["brand"] == "amex"

    by_description = {tx.description: tx for tx in result.transactions}
    # Consumo en pesos: la columna de pesos.
    merpago = by_description["MERPAGO*CAMILAPIROYANSKY"]
    assert merpago.currency == "ARS"
    assert merpago.amount_cents == 320_970
    # Percepción cobrada en pesos por un consumo en dólares.
    db_rg = by_description["DB.RG 5617 30%"]
    assert db_rg.currency == "ARS"
    assert db_rg.kind == "tax"
    assert db_rg.amount_cents == 1_318_879
    # Devolución de impuesto: importe negativo.
    devolucion = by_description["DEV.IMP. RG 5617 30%"]
    assert devolucion.amount_cents == -908_400
    assert devolucion.kind == "tax"

    # Consumo en dólares: va a suscripciones y queda en USD (no convertido).
    assert len(result.subscriptions) == 1
    apple = result.subscriptions[0]
    assert apple.currency == "USD"
    assert apple.amount_cents == 199


def test_layout_region_only_takes_marked_rows(tmp_path: Path) -> None:
    """Marcar una zona lee solo las filas de esa zona, con las columnas correctas."""
    pdf = make_two_column_statement_pdf(tmp_path / "resumen.pdf")
    pages = pdf_mod.words_pages(pdf)
    full = parse_layout(pages)
    assert full is not None
    row = next(tx for tx in full.transactions if "CAMILA" in tx.description)

    zone = {"page": 1, "x0": 60, "y0": row.bbox[1] - 2, "x1": 470, "y1": row.bbox[3] + 2}
    marked = parse_layout(pages, region=zone)
    assert marked is not None
    assert [tx.description for tx in marked.transactions] == ["MERPAGO*CAMILAPIROYANSKY"]
    assert marked.transactions[0].currency == "ARS"
    assert marked.transactions[0].amount_cents == 320_970


def test_layout_returns_none_without_text_layer(tmp_path: Path) -> None:
    """Un PDF sin capa de texto no tiene coordenadas: el pipeline usa el OCR."""
    import fitz

    doc = fitz.open()
    doc.new_page()
    empty = tmp_path / "vacio.pdf"
    doc.save(str(empty))
    doc.close()
    assert parse_layout(pdf_mod.words_pages(empty)) is None
