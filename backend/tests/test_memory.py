"""Memoria: el embedder real (embeddinggemma) cambia la dimensión de los vectores.

Regresión: `set_embedder` recibía el **método ligado** `embedder.embed`, que no
expone `dimension`, así que la dimensión quedaba en 256 (la del hashing) aunque
los vectores fueran de 768: no se rearmaban las colecciones y el primer upsert
habría fallado por dimensión.
"""

from __future__ import annotations

from pathlib import Path

from finanzar_backend.chroma_store.store import HASH_EMBEDDER, MemoryStore


class FakeEmbedder:
    """Imita a ``LlamaEmbedder``: método ``embed`` y atributo ``dimension``."""

    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        return [float(len(text) % 7)] * self.dimension


def test_set_embedder_with_bound_method_records_its_dimension(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path)
    try:
        assert memory.dim == 256
        embedder = FakeEmbedder(768)
        rebuilt = memory.set_embedder(embedder.embed, "embeddinggemma-2-768", dim=embedder.dimension)
        assert rebuilt is True, "cambia la dimensión: hay que rearmar las colecciones"
        assert memory.dim == 768
        assert memory.status()["embedder"] == "embeddinggemma-2-768"
        # El marcador queda en disco para el próximo arranque.
        assert '"dim": 768' in (tmp_path / "embedder.json").read_text(encoding="utf-8")
    finally:
        memory.reset()


def test_set_embedder_detects_dimension_from_the_instance(tmp_path: Path) -> None:
    """Sin `dim` explícito también tiene que leerlo de la instancia (``__self__``)."""
    memory = MemoryStore(tmp_path)
    try:
        rebuild = memory.set_embedder(FakeEmbedder(384).embed, "otro-384")
        assert rebuild is True
        assert memory.dim == 384
    finally:
        memory.reset()


def test_providing_the_same_embedder_again_is_a_no_op(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path)
    try:
        embedder = FakeEmbedder(768)
        assert memory.set_embedder(embedder.embed, "embeddinggemma-2-768", dim=768) is True
        assert memory.set_embedder(embedder.embed, "embeddinggemma-2-768", dim=768) is False
        assert memory.dim == 768
    finally:
        memory.reset()


def test_default_embedder_is_the_hash_one(tmp_path: Path) -> None:
    memory = MemoryStore(tmp_path)
    try:
        status = memory.status()
        assert status["embedder"] == HASH_EMBEDDER
        assert status["dimension"] == 256
    finally:
        pass


def test_reap_stale_servers_is_safe_without_orphans(tmp_path: Path) -> None:
    """La limpieza de llama-server huérfanos no falla ni mata nada ajeno."""
    from finanzar_backend.llm.llama_server import reap_stale_servers

    # Un directorio que no existe: no hay ningún servidor apuntando ahí.
    assert reap_stale_servers(tmp_path / "sin-servidores") == 0
