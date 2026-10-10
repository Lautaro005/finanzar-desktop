"""Aplicación FastAPI del backend local.

Escucha únicamente en ``127.0.0.1``. Envuelve todos los errores en el envelope
acordado y expone el ciclo de vida del contexto (migraciones, memoria, sidecar).
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api.deps import build_context
from .api.routes import router
from .config import Settings, get_settings
from .core.envelope import fail
from .core.errors import ApiError
from .core.events import bus
from .core.logging import configure_logging

logger = logging.getLogger(__name__)


def _safe_start_llama(context) -> None:  # pragma: no cover - depende del runtime
    try:
        result = context.start_llama()
        logger.info("Copiloto: %s", result)
    except Exception as exc:  # pragma: no cover
        logger.warning("No se pudo arrancar llama-server: %s", exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    configure_logging(settings.log_level, settings.logs_dir / "backend.log")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context = build_context(settings, event_bus=bus)
        app.state.ctx = context
        logger.info("Backend FinanzAR listo · datos en %s", settings.data_dir)
        # El copiloto arranca en segundo plano: la API queda disponible ya.
        threading.Thread(target=_safe_start_llama, args=(context,), daemon=True).start()
        try:
            yield
        finally:
            context.stop_llama()
            context.db.close()

    app = FastAPI(title="FinanzAR Desktop Backend", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def observe_requests(request: Request, call_next):  # pragma: no cover - observabilidad
        """Cuenta requests por cliente para auditar qué consume la ventana Tauri."""
        user_agent = request.headers.get("user-agent", "")
        if "AppleWebKit" in user_agent or "Tauri" in user_agent:
            client = "webview"
        elif "curl" in user_agent.lower():
            client = "curl"
        else:
            client = "other"
        state = getattr(request.app.state, "ctx", None)
        if state is not None:
            state.record_request(request.url.path, client)
        return await call_next(request)

    # Solo orígenes locales: la ventana Tauri y el dev server de Vite.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return fail(code=exc.code, message=exc.message, details=exc.details, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return fail(
            code="validation_error",
            message="Los datos enviados no son válidos",
            details={"errors": exc.errors()},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def generic_handler(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        logger.exception("Error no controlado")
        return fail(
            code="internal_error",
            message="Ocurrió un error inesperado en el backend local",
            details={"type": type(exc).__name__},
            status_code=500,
        )

    app.include_router(router)
    return app


app = create_app()
