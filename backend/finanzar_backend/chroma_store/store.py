"""Memoria semántica local con ChromaDB ``PersistentClient``.

Diseño:
- Embeddings **locales y offline** por *feature hashing* de n-gramas: no se
  descarga ningún modelo de embeddings, así no hay tráfico externo ni sorpresas
  de red en el primer uso.
- Los vectores se calculan acá y se pasan explícitos a Chroma, evitando depender
  de una ``EmbeddingFunction`` registrada.
- Si ``chromadb`` no está disponible, se usa un almacén JSON equivalente con la
  misma interfaz, para que la app nunca quede inutilizable.
- Metadatos obligatorios por documento: ``statement_id``, ``page``, ``period``,
  ``card_id``, ``confirmed``, ``source_type``, ``content_hash``, ``user_id``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

EMBED_DIM = 256

COLLECTIONS = ("statement_chunks", "transaction_notes", "confirmed_insights")

_TOKEN_RE = re.compile(r"[0-9a-záéíóúñü]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    words = _TOKEN_RE.findall(text.lower())
    grams: list[str] = list(words)
    for word in words:
        # n-gramas de caracteres para tolerancia a errores de OCR.
        if len(word) > 3:
            grams.extend(word[i : i + 3] for i in range(len(word) - 2))
    return grams


def embed(text: str) -> list[float]:
    """Embedding determinístico por hashing, normalizado a norma unitaria."""
    vector = [0.0] * EMBED_DIM
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % EMBED_DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _JsonFallbackStore:
    """Fallback mínimo cuando ChromaDB no está instalado."""

    def __init__(self, path: Path) -> None:
        self.file = path / "fallback_store.json"
        self.data: dict[str, list[dict[str, Any]]] = {name: [] for name in COLLECTIONS}
        if self.file.exists():
            self.data = json.loads(self.file.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def upsert(self, collection: str, docs: list[dict[str, Any]]) -> None:
        bucket = self.data.setdefault(collection, [])
        by_id = {item["id"]: item for item in bucket}
        for doc in docs:
            by_id[doc["id"]] = doc
        self.data[collection] = list(by_id.values())
        self._persist()

    def query(
        self,
        collection: str,
        embedding: list[float],
        *,
        where: dict[str, Any] | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        results = []
        for doc in self.data.get(collection, []):
            if where and not all(doc["metadata"].get(k) == v for k, v in where.items()):
                continue
            vector = doc.get("embedding") or []
            score = sum(a * b for a, b in zip(embedding, vector, strict=False))
            results.append(
                {
                    "id": doc["id"],
                    "document": doc["document"],
                    "metadata": doc["metadata"],
                    "distance": 1 - score,
                }
            )
        results.sort(key=lambda item: item["distance"])
        return results[:limit]

    def count(self, collection: str) -> int:
        return len(self.data.get(collection, []))

    def delete(self, collection: str, where: dict[str, Any]) -> None:
        bucket = self.data.get(collection, [])
        self.data[collection] = [
            doc for doc in bucket if not all(doc["metadata"].get(k) == v for k, v in where.items())
        ]
        self._persist()


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.backend = "chromadb"
        self._client: Any = None
        self._collections: dict[str, Any] = {}
        self._fallback: _JsonFallbackStore | None = None
        try:  # pragma: no cover - depende del entorno
            import chromadb  # type: ignore

            self._client = chromadb.PersistentClient(path=str(self.path))
            for name in COLLECTIONS:
                self._collections[name] = self._client.get_or_create_collection(
                    name=name, metadata={"hnsw:space": "cosine"}
                )
        except Exception:  # pragma: no cover - fallback honesto
            self.backend = "json-fallback"
            self._fallback = _JsonFallbackStore(self.path)

    # -- escritura --------------------------------------------------------
    def index_document(
        self,
        collection: str,
        *,
        doc_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> str:
        if collection not in COLLECTIONS:
            raise ValueError(f"Colección desconocida: {collection}")
        content_hash = _content_hash(text)
        enriched = {**metadata, "content_hash": content_hash, "confirmed": bool(metadata.get("confirmed", False))}
        # Chroma no admite None en metadatos.
        enriched = {k: ("__none__" if v is None else v) for k, v in enriched.items()}
        if self._fallback is not None:
            self._fallback.upsert(
                collection,
                [{"id": doc_id, "document": text, "metadata": enriched, "embedding": embed(text)}],
            )
            return content_hash
        self._collections[collection].upsert(
            ids=[doc_id],
            documents=[text],
            embeddings=[embed(text)],
            metadatas=[enriched],
        )
        return content_hash

    def index_many(self, collection: str, docs: Iterable[dict[str, Any]]) -> int:
        count = 0
        for doc in docs:
            self.index_document(
                collection,
                doc_id=doc["id"],
                text=doc["text"],
                metadata=doc["metadata"],
            )
            count += 1
        return count

    # -- lectura ----------------------------------------------------------
    def query(
        self,
        collection: str,
        text: str,
        *,
        period: str | None = None,
        confirmed_only: bool = True,
        card_id: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        if collection not in COLLECTIONS:
            raise ValueError(f"Colección desconocida: {collection}")
        where: dict[str, Any] = {}
        if period:
            where["period"] = period
        if card_id:
            where["card_id"] = card_id
        if confirmed_only:
            where["confirmed"] = True
        embedding = embed(text)
        if self._fallback is not None:
            return self._fallback.query(collection, embedding, where=where or None, limit=limit)
        clauses = [{key: value} for key, value in where.items()]
        where_clause: Any = None
        if len(clauses) == 1:
            where_clause = clauses[0]
        elif len(clauses) > 1:
            where_clause = {"$and": clauses}
        result = self._collections[collection].query(
            query_embeddings=[embedding],
            n_results=limit,
            where=where_clause,
        )
        output: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for index, doc_id in enumerate(ids):
            output.append(
                {
                    "id": doc_id,
                    "document": documents[index],
                    "metadata": metadatas[index],
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return output

    def count(self, collection: str) -> int:
        if self._fallback is not None:
            return self._fallback.count(collection)
        return int(self._collections[collection].count())

    def delete_where(self, collection: str, where: dict[str, Any]) -> None:
        if self._fallback is not None:
            self._fallback.delete(collection, where)
            return
        self._collections[collection].delete(where=where)

    def reset(self) -> None:
        if self._fallback is not None:
            for name in COLLECTIONS:
                self._fallback.data[name] = []
            self._fallback._persist()
            return
        for name in COLLECTIONS:
            self._client.delete_collection(name)
            self._collections[name] = self._client.get_or_create_collection(
                name=name, metadata={"hnsw:space": "cosine"}
            )
