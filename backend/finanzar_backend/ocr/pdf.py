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


@dataclass
class PageWords:
    """Palabras con coordenadas: permite reconstruir las columnas del resumen."""

    number: int  # 1-indexado
    width: float
    height: float
    words: list[dict[str, object]]


def words_pages(pdf_path: Path, max_pages: int = 40) -> list[PageWords]:
    """Palabras con bbox por página (coordenadas en puntos PDF).

    Se agrupan por (bloque, línea) para reconstruir cada renglón del resumen y
    distinguir la columna de pesos de la de dólares por posición horizontal.
    """
    fitz = _import_fitz()
    pages: list[PageWords] = []
    with fitz.open(str(pdf_path)) as doc:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            rect = page.rect
            words: list[dict[str, object]] = []
            for x0, y0, x1, y1, text, block_no, line_no, word_no in page.get_text("words"):
                cleaned = str(text).strip()
                if not cleaned:
                    continue
                words.append(
                    {
                        "text": cleaned,
                        "x0": round(float(x0), 1),
                        "y0": round(float(y0), 1),
                        "x1": round(float(x1), 1),
                        "y1": round(float(y1), 1),
                        "block": int(block_no),
                        "line": int(line_no),
                        "index": int(word_no),
                    }
                )
            pages.append(
                PageWords(number=index + 1, width=float(rect.width), height=float(rect.height), words=words)
            )
    return pages


def page_text_in_rect(pdf_path: Path, page_number: int, rect: tuple[float, float, float, float]) -> str:
    """Texto nativo dentro de un rectángulo (puntos PDF) de una página."""
    fitz = _import_fitz()
    with fitz.open(str(pdf_path)) as doc:
        if not 1 <= page_number <= doc.page_count:
            return ""
        page = doc[page_number - 1]
        return page.get_text("text", clip=fitz.Rect(*rect))


def page_png(pdf_path: Path, page_number: int, dpi: int = 150) -> tuple[bytes, int, int]:
    """PNG de una página a cierta resolución, con su ancho y alto en píxeles."""
    fitz = _import_fitz()
    with fitz.open(str(pdf_path)) as doc:
        if not 1 <= page_number <= doc.page_count:
            raise ValueError(f"La página {page_number} no existe")
        page = doc[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
        return pixmap.tobytes("png"), pixmap.width, pixmap.height


def page_size(pdf_path: Path, page_number: int) -> tuple[float, float]:
    """Tamaño de una página en puntos PDF (para mapear bbox a píxeles)."""
    fitz = _import_fitz()
    with fitz.open(str(pdf_path)) as doc:
        if not 1 <= page_number <= doc.page_count:
            raise ValueError(f"La página {page_number} no existe")
        rect = doc[page_number - 1].rect
        return float(rect.width), float(rect.height)


def render_region(
    pdf_path: Path, page_number: int, rect: tuple[float, float, float, float], dpi: int = 300
) -> RenderedPage | None:
    """Recorta un rectángulo (puntos PDF) de una página como PNG."""
    fitz = _import_fitz()
    with fitz.open(str(pdf_path)) as doc:
        if not 1 <= page_number <= doc.page_count:
            return None
        page = doc[page_number - 1]
        clip = fitz.Rect(*rect) & page.rect
        if clip.is_empty:
            return None
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), clip=clip, alpha=False)
        return RenderedPage(
            number=page_number, png=pixmap.tobytes("png"), width=pixmap.width, height=pixmap.height
        )
