"""Contexto de la aplicación y utilidades de inyección de dependencias."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from ..chroma_store.store import MemoryStore
from ..config import Settings, get_settings, repo_root
from ..core.events import EventBus
from ..core.events import bus as global_bus
from ..db.repo import Repository
from ..db.sqlite import Database
from ..finance.engine import FinanceEngine, period_of, today
from ..finance.insights import refresh_insights
from ..llm.client import LlamaClient
from ..llm.copilot import Copilot
from ..llm.embedder import start_embedding_server
from ..llm.llama_server import LlamaConfig, LlamaServer, free_port, resolve_binary
from ..models.downloader import ModelDownloader
from ..ocr.pipeline import DocumentPipeline
from ..updates import UpdateChecker

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    repo: Repository
    engine: FinanceEngine
    memory: MemoryStore
    bus: EventBus
    pipeline: DocumentPipeline
    downloader: ModelDownloader
    update_checker: UpdateChecker
    llama_client: LlamaClient | None = None
    llama_server: LlamaServer | None = None
    llama_port: int | None = None
    embedder: Any = None
    embedding_server: LlamaServer | None = None
    version: str = __version__
    copilot_factory: Any = None
    request_stats: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Lock propio de los embeddings: arrancar el servidor tarda y no debe
    # bloquear el registro de pedidos (que usa ``_lock``).
    _embedding_lock: threading.Lock = field(default_factory=threading.Lock)

    def record_request(self, path: str, client: str) -> None:
        with self._lock:
            key = f"{client} {path}"
            self.request_stats[key] = self.request_stats.get(key, 0) + 1

    # -- ciclo de vida ----------------------------------------------------
    def start_llama(self) -> dict[str, Any]:
        """Intenta arrancar llama-server si el binario y el modelo existen."""
        from ..models.manifest import load_manifest

        manifest = load_manifest()
        llm = manifest.model("spark-x2.5-1.7b")
        quant = llm.default_quantization or llm.quantizations[0].name
        model_path = self.settings.models_dir / llm.id / llm.revision / quant / llm.quantization(quant).file
        binary = resolve_binary(
            self.settings.binary_dir, repo_root() / "models", build=manifest.runtime["llamaCpp"].build
        )
        if binary is None or not model_path.exists():
            logger.info("llama-server no disponible (binario=%s, modelo=%s)", binary, model_path.exists())
            return {"started": False, "reason": "runtime_or_model_missing"}
        port = free_port()
        server = LlamaServer(
            binary,
            LlamaConfig(
                model_path=model_path,
                port=port,
                context_size=self.settings.llm_context_size,
                threads=self.settings.llm_threads,
            ),
        )
        started = server.start(log_path=self.settings.logs_dir / "llama-server.log")
        if started:
            self.llama_server = server
            self.llama_client = LlamaClient(server.base_url)
            self.llama_port = port
        return {"started": started, "port": port}

    def stop_llama(self) -> None:
        if self.llama_server is not None:
            self.llama_server.stop()
            self.llama_server = None
            self.llama_client = None
            self.llama_port = None

    # -- embeddings locales (embeddinggemma-2) ----------------------------
    def embeddings_model(self) -> tuple[Any, Any] | None:
        """(binario, GGUF) de embeddinggemma-2 si el modelo y el runtime están."""
        from ..models.manifest import load_manifest

        manifest = load_manifest()
        try:
            spec = manifest.model("embeddinggemma-2")
        except KeyError:  # pragma: no cover - manifest sin el modelo
            return None
        quant = spec.quantization(spec.default_quantization)
        model_path = self.settings.models_dir / spec.id / spec.revision / quant.name / quant.file
        binary = resolve_binary(
            self.settings.binary_dir, repo_root() / "models", build=manifest.runtime["llamaCpp"].build
        )
        if binary is None or not model_path.exists():
            return None
        return binary, model_path

    def embeddings_status(self) -> dict[str, Any]:
        installed = self.embeddings_model() is not None
        return {
            "installed": installed,
            "available": bool(self.embedder is not None and self.embedder.available()),
            "model": "embeddinggemma-2" if installed else None,
            "memory": self.memory.status(),
        }

    def start_embeddings(self) -> dict[str, Any]:
        """Levanta el servidor de embeddings y activa los vectores reales.

        Es opcional: si el modelo no está descargado o el runtime no lo soporta,
        la memoria sigue con el embedding por hashing (sin modelos).
        """
        with self._embedding_lock:
            if self.embedder is not None and self.embedder.available():
                return {"started": False, "reason": "already_running", **self.embeddings_status()}
            found = self.embeddings_model()
            if found is None:
                return {"started": False, "reason": "model_or_runtime_missing", **self.embeddings_status()}
            binary, model_path = found
            started = start_embedding_server(
                binary, model_path, log_path=self.settings.logs_dir / "embeddings.log"
            )
            if started is None:
                logger.warning("No se pudo iniciar el servidor de embeddings")
                return {"started": False, "reason": "server_failed", **self.embeddings_status()}
            server, embedder = started
            self.embedding_server = server
            self.embedder = embedder
            rebuilt = self.memory.set_embedder(embedder.embed, "embeddinggemma-2-768")
        if rebuilt:
            # Cambió la dimensión: los fragmentos viejos no sirven y se reindexan.
            try:
                self.pipeline.reindex_memory()
            except Exception as exc:  # pragma: no cover - mejor seguir andando
                logger.warning("No se pudo reindexar la memoria: %s", exc)
        return {"started": True, "rebuilt": rebuilt, **self.embeddings_status()}

    def stop_embeddings(self) -> None:
        if self.embedding_server is not None:
            self.embedding_server.stop()
            self.embedding_server = None
            self.embedder = None

    def copilot(self) -> Copilot:
        return Copilot(
            self.repo,
            self.engine,
            self.memory,
            self.llama_client,
            user_name=self.repo.get_setting("user_name"),
        )


def build_context(settings: Settings | None = None, *, event_bus: EventBus | None = None) -> AppContext:
    settings = settings or get_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.migrate()
    repo = Repository(db)
    engine = FinanceEngine(repo)
    memory = MemoryStore(settings.chroma_path)
    event_bus = event_bus or global_bus
    pipeline = DocumentPipeline(settings, repo, engine, memory, event_bus)
    downloader = ModelDownloader(settings, event_bus)
    checker = UpdateChecker(settings, __version__)
    engine.apply_recurring_income()
    refresh_insights(engine, period_of(today()))
    context = AppContext(
        settings=settings,
        db=db,
        repo=repo,
        engine=engine,
        memory=memory,
        bus=event_bus,
        pipeline=pipeline,
        downloader=downloader,
        update_checker=checker,
    )
    # Los embeddings reales (embeddinggemma-2) se levantan en segundo plano: si el
    # modelo no está, la app arranca igual con el embedding por hashing.
    threading.Thread(target=context.start_embeddings, daemon=True).start()
    return context


def resolve_document_path(settings: Settings, requested: str) -> Path:
    """Valida que una ruta esté dentro del directorio de documentos.

    Impide path traversal: la ruta resuelta debe quedar contenida en el
    directorio de documentos de la aplicación.
    """
    from ..core.errors import PathNotAllowedError

    base = settings.documents_dir.resolve()
    candidate = Path(requested)
    candidate = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if base not in candidate.parents and candidate != base:
        raise PathNotAllowedError("La ruta solicitada está fuera del directorio permitido")
    return candidate
