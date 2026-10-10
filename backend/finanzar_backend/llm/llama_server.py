"""Gestión del runtime ``llama-server`` de llama.cpp en loopback.

Resuelve el binario por target de macOS, arranca el servidor OpenAI-compatible
en ``127.0.0.1`` con un puerto libre y espera el health check. Si el runtime o el
modelo no están, el copiloto queda marcado como no disponible sin bloquear el
resto de la app.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def current_target() -> str:
    machine = platform.machine().lower()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    return f"{arch}-apple-darwin"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class LlamaConfig:
    model_path: Path
    port: int
    context_size: int = 8192
    threads: int = 0
    binary: Path | None = None
    # Modo embeddings (embeddinggemma-2): el servidor no genera texto, devuelve
    # vectores en ``/v1/embeddings``.
    embedding: bool = False
    pooling: str | None = None


class LlamaServer:
    def __init__(self, binary: Path, config: LlamaConfig) -> None:
        self.binary = binary
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self.log_path: Path | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.config.port}"

    def is_healthy(self, timeout: float = 1.0) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def start(self, log_path: Path | None = None, wait_seconds: float = 60.0) -> bool:
        if self.is_healthy():
            return True
        args = [
            str(self.binary),
            "-m",
            str(self.config.model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.config.port),
            "-c",
            str(self.config.context_size),
        ]
        if self.config.threads:
            args += ["-t", str(self.config.threads)]
        if self.config.embedding:
            args += ["--embedding"]
            if self.config.pooling:
                args += ["--pooling", self.config.pooling]
        self.log_path = log_path
        handle = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = log_path.open("ab")
        self.process = subprocess.Popen(
            args,
            stdout=handle or subprocess.DEVNULL,
            stderr=handle or subprocess.DEVNULL,
            env={**os.environ, "LLAMA_LOG_LEVEL": "warn"},
        )
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self.process.poll() is not None:
                logger.warning("llama-server terminó con código %s", self.process.returncode)
                return False
            if self.is_healthy():
                logger.info("llama-server escuchando en %s", self.base_url)
                return True
            time.sleep(0.5)
        return False

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self.process.kill()
        self.process = None


def resolve_binary(binary_dir: Path, repo_models_dir: Path | None = None, build: str | None = None) -> Path | None:
    """Busca ``llama-server`` en: override, datos de la app, repo o PATH.

    ``build`` es la build fijada en el manifest: si se indica, se prefiere esa
    carpeta (``llama-<build>``) para no quedarse con una build vieja que quedó
    descargada en el mismo directorio.
    """
    override = os.environ.get("FINANZAR_LLAMA_SERVER")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    target = current_target()
    if build:
        candidates += [
            binary_dir / "llama-server" / f"llama-{build}" / "llama-server",
            binary_dir / "llama-server" / build / "llama-server",
        ]
        if repo_models_dir is not None:
            candidates.append(repo_models_dir / "llama-server" / f"llama-{build}" / "llama-server")
    candidates += [
        binary_dir / "llama-server" / "build" / "bin" / "llama-server",
        binary_dir / "llama-server" / target / "llama-server",
    ]
    if repo_models_dir is not None:
        candidates += [
            repo_models_dir / "llama-server" / target / "llama-server",
            repo_models_dir / "llama-server" / "llama-server",
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    which = shutil.which("llama-server")
    if which:
        return Path(which)
    # Último recurso: cualquier llama-server dentro de binary_dir.
    if binary_dir.exists():
        found = sorted(binary_dir.rglob("llama-server"))
        if found:
            return found[0]
    return None


def reap_stale_servers(data_dir: Path) -> int:
    """Apaga los ``llama-server`` que quedaron de una corrida anterior.

    Al cerrar la ventana, el shell mata el backend (SIGKILL) y sus
    ``llama-server`` —copiloto y embeddings— quedan vivos, ocupando memoria sin
    que nadie les hable. Al arrancar de nuevo se apagan los que apuntan a nuestro
    directorio de datos (devuelve cuántos encontró).

    En Windows no hay ``pgrep``: se omite sin ruido.
    """
    if platform.system() == "Windows":  # pragma: no cover - sólo Windows
        return 0
    pattern = f"llama-server.*{data_dir}"
    try:
        found = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - sin pgrep
        return 0
    killed = 0
    for token in found.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            logger.info("Apagado un llama-server huérfano (pid %s)", pid)
        except OSError:
            continue
    return killed
