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
    version: str = __version__
    copilot_factory: Any = None
    request_stats: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
        binary = resolve_binary(self.settings.binary_dir, repo_root() / "models")
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

    def copilot(self) -> Copilot:
        return Copilot(self.repo, self.engine, self.memory, self.llama_client)


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
    return AppContext(
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
