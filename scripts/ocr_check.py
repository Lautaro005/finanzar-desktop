#!/usr/bin/env python
"""Prueba GLM-OCR real sobre un PDF de resumen.

    cd backend && uv run python ../scripts/ocr_check.py

Genera un PDF con el formato de un resumen argentino, lo pasa por el pipeline
(render + GLM-OCR + extracción) y muestra motor, campos, confianza y evidencia.
Requiere el extra `ocr` instalado y los pesos descargados.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from finanzar_backend.api.deps import build_context  # noqa: E402
from finanzar_backend.config import Settings, default_data_dir  # noqa: E402

LINES = [
    "BANCO GALICIA - VISA",
    "Resumen de cuenta",
    "Periodo: 2026-10",
    "Fecha de cierre: 28/10/2026",
    "Vencimiento actual: 10/10/2026",
    "Total a pagar: 218.450,00",
    "Pago minimo: 43.690,00",
    "Detalle de consumos:",
    "08/10/2026 Mercado La Plaza 42.860,00",
    "04/10/2026 Streaming Max 8.990,00",
    "03/10/2026 Cuota notebook 04/12 94.700,00",
    "02/10/2026 Farmacity 16.420,00",
]


def make_pdf(path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 70
    for line in LINES:
        page.insert_text((60, y), line, fontsize=11)
        y += 20
    doc.save(str(path))
    doc.close()
    return path


def main() -> int:
    settings = Settings(data_dir=default_data_dir(), log_level="WARNING")
    settings.ensure_dirs()
    context = build_context(settings)
    try:
        model_dir = context.pipeline.glm_model_dir()
        print(f"Directorio de GLM-OCR: {model_dir}")
        if model_dir is None:
            print("✗ No se encontraron los pesos de GLM-OCR")
            return 1

        from finanzar_backend.ocr.glm_ocr import GlmOcrEngine

        engine = GlmOcrEngine(model_dir)
        print(f"¿GLM-OCR disponible? {engine.available()}")
        if not engine.available():
            print("✗ Falta torch/transformers o los pesos; instalá el extra [ocr]")
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            pdf = make_pdf(Path(tmp) / "resumen-galicia.pdf")
            print(f"PDF de prueba: {pdf}")
            statement = context.pipeline.import_document(pdf.name, pdf.read_bytes())
            print(f"Documento importado: {statement['id']}")

            import asyncio

            result = asyncio.run(context.pipeline.run_ocr(statement["id"], prefer="glm"))
            print("\n=== Resultado del pipeline ===")
            for key, value in result.items():
                print(f"  {key}: {value}")

            from finanzar_backend.ocr.glm_ocr import build_engine
            from finanzar_backend.ocr import pdf as pdf_mod

            engine = build_engine(pdf, glm_model_dir=model_dir, prefer="glm")
            pages = pdf_mod.render_pages(pdf)
            page_texts = engine.run(pages)
            print(f"\n=== Texto crudo del OCR ({engine.name}) ===")
            for page in page_texts:
                print(page.text[:1400])
                print("---- fin de página ----")

            review = context.pipeline.review(statement["id"])
            document_transactions = [
                tx for tx in review["transactions"] if tx.get("statement_id") == statement["id"]
            ]
            print("\n=== Campos extraídos (con confianza y evidencia) ===")
            for field in review["fields"]:
                confidence = field["confidence"]
                conf = f"{round(confidence * 100)}%" if confidence is not None else "—"
                print(
                    f"  {field['field_key']:12} = {str(field['field_value'])[:40]:40} "
                    f"conf={conf:>4} pag={field['source_page']}"
                )
                if field.get("evidence_text"):
                    print(f"      evidencia: {field['evidence_text'][:90]}")

            print("\n=== Movimientos detectados ===")
            for tx in document_transactions:
                print(f"  {tx['occurred_on']} {tx['description'][:32]:32} {tx['amount_cents']:>12} {tx['kind']}")

            engine_name = result.get("engine")
            print(f"\nMotor usado: {engine_name}")
            print(f"Movimientos del documento: {len(document_transactions)}")
            ok = engine_name == "glm-ocr"
            print("RESULTADO:", "GLM-OCR REAL OK" if ok else "DEGRADÓ A TEXTO NATIVO")
            return 0 if ok else 2
    finally:
        context.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
