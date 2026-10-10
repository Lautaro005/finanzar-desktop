"""Embeddings locales con ``llama-server`` (embeddinggemma-2).

El copiloto indexa los resúmenes confirmados y busca por similitud. Por defecto
usa un embedding por *feature hashing* (sin modelos, pero sólo léxico). Cuando la
persona descarga ``embeddinggemma-2`` se levanta un segundo ``llama-server`` en
modo embeddings y la memoria pasa a usar vectores reales de 768 dimensiones.

Requiere una build de llama.cpp con soporte del modelo: verificado el
2026-10-10 con ``b11552`` (la ``b10828`` no lo carga).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from .llama_server import LlamaConfig, LlamaServer

logger = logging.getLogger(__name__)

EMBEDDINGS_ID = "embeddinggemma-2"


class LlamaEmbedder:
    """Cliente de embeddings sobre ``llama-server``."""

    def __init__(self, base_url: str, dimension: int = 768, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.dimension = dimension
        self.timeout = timeout

    def available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": text[:8000], "model": "embeddinggemma"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        data = payload.get("data") or []
        if not data:
            raise RuntimeError("El servidor de embeddings no devolvió vectores")
        return [float(value) for value in data[0].get("embedding") or []]


def embeddings_model_path(models_dir: Path, model_id: str, revision: str, filename: str) -> Path:
    """Ruta esperada del GGUF de embeddings dentro del directorio de modelos."""
    return models_dir / model_id / revision / "Q8_0" / filename


def start_embedding_server(
    binary: Path,
    model_path: Path,
    *,
    log_path: Path | None = None,
) -> tuple[LlamaServer, LlamaEmbedder] | None:
    """Levanta el servidor de embeddings y devuelve su cliente, o ``None``."""
    from .llama_server import free_port

    port = free_port()
    server = LlamaServer(
        binary,
        LlamaConfig(model_path=model_path, port=port, context_size=2048, embedding=True, pooling="mean"),
    )
    if not server.start(log_path=log_path):
        return None
    return server, LlamaEmbedder(server.base_url)
