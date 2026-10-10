"""Fixtures compartidas de la suite Python.

Se fija ``FINANZAR_DATA_DIR`` a un directorio temporal **antes** de importar el
paquete para que el ``app`` a nivel de módulo no escriba en el directorio real
del usuario.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_SESSION_TMP = tempfile.mkdtemp(prefix="finanzar-tests-")
os.environ.setdefault("FINANZAR_DATA_DIR", _SESSION_TMP)
os.environ.setdefault("FINANZAR_LOG_LEVEL", "WARNING")
os.environ.setdefault("FINANZAR_ALLOW_SEED", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from finanzar_backend.api.deps import build_context  # noqa: E402
from finanzar_backend.config import Settings, reset_settings_cache  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    reset_settings_cache()
    os.environ["FINANZAR_DATA_DIR"] = str(tmp_path)
    value = Settings(data_dir=tmp_path, log_level="WARNING")
    value.ensure_dirs()
    return value


@pytest.fixture
def context(settings: Settings):
    ctx = build_context(settings)
    try:
        yield ctx
    finally:
        ctx.db.close()


@pytest.fixture
def client(settings: Settings):
    from finanzar_backend.main import create_app

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def make_statement_pdf(path: Path) -> Path:
    """Genera un PDF de resumen con capa de texto para los tests de OCR."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "BANCO GALICIA - VISA",
        "Resumen de cuenta",
        "Periodo: 2026-10",
        "Fecha de cierre: 28/10/2026",
        "Vencimiento actual: 10/10/2026",
        "Total a pagar: 218.450,00",
        "Pago minimo: 43.690,00",
        "Detalle de consumos",
        "08/10/2026 Mercado La Plaza 42.860,00",
        "04/10/2026 Streaming Max 8.990,00",
        "03/10/2026 Cuota notebook 04/12 94.700,00",
        "02/10/2026 Farmacity 16.420,00",
        "USD 29,00 Adobe Creative Cloud",
    ]
    text = "\n".join(lines)
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()
    return path
