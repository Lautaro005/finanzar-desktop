"""Runner de GLM-OCR (carga directa, sin pipeline ``image-to-text``).

El model card de ``zai-org/GLM-OCR`` documenta la carga directa con
``AutoProcessor`` + ``GlmOcrForConditionalGeneration`` en Transformers 5. Este
módulo usa esa ruta. Si ``torch``/``transformers`` o el modelo no están
disponibles, devuelve ``None`` y el pipeline degrada al texto nativo del PDF
(marcando el motor usado, nunca simulando confianza).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .pdf import RenderedPage

logger = logging.getLogger(__name__)

TEXT_PROMPT = "Text Recognition:"
TABLE_PROMPT = "Table Recognition:"


@dataclass
class PageText:
    number: int
    text: str
    engine: str
    confidence: float | None = None
    bbox: list[float] | None = None


class OcrEngine(Protocol):
    name: str

    def available(self) -> bool: ...

    def run(self, pages: list[RenderedPage], prompt: str = TEXT_PROMPT) -> list[PageText]: ...


class HeuristicEngine:
    """Motor de respaldo: texto nativo del PDF vía PyMuPDF.

    No es OCR real para PDFs escaneados, pero para PDFs con capa de texto
    devuelve el contenido verdadero del documento. Se identifica explícitamente
    como ``native-pymupdf`` para no confundirlo con el modelo.
    """

    name = "native-pymupdf"

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path

    def available(self) -> bool:
        return True

    def run(self, pages: list[RenderedPage], prompt: str = TEXT_PROMPT) -> list[PageText]:
        from .pdf import extract_text_pages

        _ = pages, prompt
        return [
            PageText(number=page.number, text=page.text, engine=self.name, confidence=None)
            for page in extract_text_pages(self.pdf_path)
        ]


class GlmOcrEngine:
    """Carga directa de GLM-OCR desde el directorio local de modelos."""

    name = "glm-ocr"

    def __init__(self, model_dir: Path, *, max_new_tokens: int = 2048, device: str | None = None) -> None:
        self.model_dir = model_dir
        self.max_new_tokens = max_new_tokens
        self.device = device
        self._processor: Any = None
        self._model: Any = None
        self._torch: Any = None

    def available(self) -> bool:
        if not (self.model_dir / "model.safetensors").exists() and not (self.model_dir / "config.json").exists():
            return False
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
        except Exception:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch  # type: ignore
        from transformers import AutoProcessor, GlmOcrForConditionalGeneration  # type: ignore

        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(str(self.model_dir))
        kwargs: dict[str, Any] = {"device_map": "auto"}
        if self.device:
            kwargs = {"torch_dtype": torch.float32}
        self._model = GlmOcrForConditionalGeneration.from_pretrained(str(self.model_dir), **kwargs)

    def run(self, pages: list[RenderedPage], prompt: str = TEXT_PROMPT) -> list[PageText]:
        import io
        import re

        from PIL import Image

        self._ensure_loaded()
        results: list[PageText] = []
        for page in pages:
            image = Image.open(io.BytesIO(page.png)).convert("RGB")
            messages = [
                {
                    "role": "user",
                    "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}],
                }
            ]
            inputs = self._processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self._model.device)
            prompt_length = inputs["input_ids"].shape[1]
            with self._torch.no_grad():
                output = self._model.generate(**inputs, max_new_tokens=self.max_new_tokens)
            # Solo los tokens generados: decodificar la secuencia completa mete los
            # marcadores <|image|> del input en el texto.
            generated = output[0][prompt_length:]
            decoded = self._processor.decode(generated, skip_special_tokens=True)
            decoded = re.sub(r"<\|[^|]*\|>", " ", decoded)
            results.append(
                PageText(
                    number=page.number,
                    text=self._dedupe_lines(decoded),
                    engine=self.name,
                    confidence=None,
                    bbox=[0.0, 0.0, float(page.width), float(page.height)],
                )
            )
        return results

    @staticmethod
    def _dedupe_lines(text: str) -> str:
        """Colapsa líneas idénticas repetidas por el decodificador."""
        seen: set[str] = set()
        lines: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
        return "\n".join(lines)


def build_engine(
    pdf_path: Path,
    *,
    glm_model_dir: Path | None,
    prefer: str = "auto",
) -> OcrEngine:
    """Elige el motor: GLM-OCR si está disponible, si no el texto nativo."""
    if prefer in {"auto", "glm"} and glm_model_dir is not None:
        glm = GlmOcrEngine(glm_model_dir)
        if glm.available():
            return glm
        if prefer == "glm":
            logger.warning("GLM-OCR pedido pero no disponible; se usa texto nativo del PDF")
    return HeuristicEngine(pdf_path)
