"""Render de páginas PDF e imágenes y extracción de texto nativo.

Se usa PyMuPDF (``fitz``), que no requiere dependencias de sistema como poppler.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_DPI = 200
MAX_LONG_EDGE = 2048


@dataclass
class RenderedPage:
    number: int  # 1-indexado
    png: bytes
    width: int
    height: int


@dataclass
class TextPage:
    number: int
    text: str


def _import_fitz():
    try:
        import fitz  # type: ignore

        return fitz
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "PyMuPDF no está instalado. Ejecutá la instalación del backend (uv sync)."
        ) from exc


def render_pages(pdf_path: Path, dpi: int = DEFAULT_DPI, max_pages: int = 40) -> list[RenderedPage]:
    fitz = _import_fitz()
    pages: list[RenderedPage] = []
    with fitz.open(str(pdf_path)) as doc:
        scale = dpi / 72.0
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            matrix = fitz.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            width, height = pixmap.width, pixmap.height
            if max(width, height) > MAX_LONG_EDGE:
                ratio = MAX_LONG_EDGE / max(width, height)
                matrix = fitz.Matrix(scale * ratio, scale * ratio)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                width, height = pixmap.width, pixmap.height
            pages.append(RenderedPage(number=index + 1, png=pixmap.tobytes("png"), width=width, height=height))
    return pages


def extract_text_pages(pdf_path: Path, max_pages: int = 40) -> list[TextPage]:
    fitz = _import_fitz()
    pages: list[TextPage] = []
    with fitz.open(str(pdf_path)) as doc:
        metadata = doc.metadata or {}
        _ = metadata
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            pages.append(TextPage(number=index + 1, text=page.get_text("text")))
    return pages


def page_count(pdf_path: Path) -> int:
    fitz = _import_fitz()
    with fitz.open(str(pdf_path)) as doc:
        return doc.page_count


def page_blocks(pdf_path: Path, max_pages: int = 40) -> list[dict]:
    """Bloques de texto con bounding box por página (fuente de evidencia)."""
    fitz = _import_fitz()
    output: list[dict] = []
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
                output.append(
                    {
                        "page": index + 1,
                        "text": str(text).strip(),
                        "bbox": [round(float(x0), 1), round(float(y0), 1), round(float(x1), 1), round(float(y1), 1)],
                    }
                )
    return output
