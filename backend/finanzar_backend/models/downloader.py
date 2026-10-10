"""Descargador de modelos reanudable, verificable y cancelable.

Usa ``huggingface_hub.hf_hub_download`` (que ya implementa reanudación y cache
por revisión) cuando está disponible. Si no, cae a HTTP por rangos con
``httpx``. En ambos casos verifica tamaño y SHA256 antes de dar el modelo por
instalado, y registra el resultado en ``model_installations``.
"""

from __future__ import annotations

import logging
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..core.events import EventBus, Job
from .manifest import Manifest, ModelSpec, load_manifest

logger = logging.getLogger(__name__)

CHUNK = 4 * 1024 * 1024
MIN_FREE_MARGIN = 512 * 1024 * 1024


class DownloadCancelled(RuntimeError):
    pass


@dataclass
class DownloadState:
    cancelled: bool = False
    job: Job | None = None


@dataclass
class ModelStatus:
    id: str
    name: str
    kind: str
    required: bool
    revision: str
    license: str
    approx_bytes: int
    installed: bool = False
    verified: bool = False
    path: str | None = None
    size_bytes: int = 0
    status: str = "missing"
    notes: str = ""
    quantization: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "revision": self.revision,
            "license": self.license,
            "approxBytes": self.approx_bytes,
            "installed": self.installed,
            "verified": self.verified,
            "path": self.path,
            "sizeBytes": self.size_bytes,
            "status": self.status,
            "notes": self.notes,
            "quantization": self.quantization,
            **self.extra,
        }


def free_bytes(path: Path) -> int:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(target).free


class ModelDownloader:
    def __init__(self, settings: Settings, bus: EventBus, manifest: Manifest | None = None) -> None:
        self.settings = settings
        self.bus = bus
        self.manifest = manifest or load_manifest()
        self._states: dict[str, DownloadState] = {}

    # -- estado -----------------------------------------------------------
    def _model_dir(self, spec: ModelSpec, quantization: str | None = None) -> Path:
        base = self.settings.models_dir / spec.id / spec.revision
        if quantization:
            base = base / quantization
        return base

    def status(self, spec: ModelSpec, quantization: str | None = None) -> ModelStatus:
        quant = spec.default_quantization if spec.kind == "llm" else None
        if spec.kind == "llm" and quantization:
            quant = quantization
        directory = self._model_dir(spec, quant)
        status = ModelStatus(
            id=spec.id,
            name=spec.name,
            kind=spec.kind,
            required=spec.required,
            revision=spec.revision,
            license=spec.license,
            approx_bytes=spec.approx_bytes,
            notes=spec.notes,
            quantization=quant,
        )
        marker = directory / ".verified.json"
        if marker.exists():
            status.installed = True
            status.verified = True
            status.status = "installed"
            status.path = str(directory)
            status.size_bytes = sum(
                f.stat().st_size for f in directory.rglob("*") if f.is_file() and f.name != ".verified.json"
            )
        return status

    def statuses(self, quantization: str | None = None) -> list[dict[str, Any]]:
        return [self.status(spec, quantization).to_dict() for spec in self.manifest.models]

    # -- cancelación ------------------------------------------------------
    def cancel(self, model_id: str) -> bool:
        state = self._states.get(model_id)
        if state is None:
            return False
        state.cancelled = True
        return True

    # -- descarga ---------------------------------------------------------
    async def download(self, model_id: str, quantization: str | None = None) -> dict[str, Any]:
        spec = self.manifest.model(model_id)
        custom = self.status(spec, quantization)
        if custom.installed:
            return {"model": custom.to_dict(), "alreadyInstalled": True}

        quant = None
        if spec.kind == "llm":
            quant = spec.quantization(quantization)
        directory = self._model_dir(spec, quant.name if quant else None)
        directory.mkdir(parents=True, exist_ok=True)

        total = quant.bytes if quant else spec.approx_bytes
        free = free_bytes(self.settings.models_dir)
        if free < total + MIN_FREE_MARGIN:
            raise RuntimeError(
                f"Espacio insuficiente para {spec.name}: se necesitan "
                f"{(total + MIN_FREE_MARGIN) // (1024 * 1024)} MB libres."
            )

        state = DownloadState()
        job = await self.bus.create_job(
            "model_download",
            {"modelId": spec.id, "quantization": quant.name if quant else None},
        )
        state.job = job
        self._states[spec.id] = state
        await self.bus.update_job(job, status="running", progress=0.0, message=f"Descargando {spec.name}")

        try:
            if quant is not None:
                await self._download_llm(spec, quant, directory, job, state)
            else:
                await self._download_repo(spec, directory, job, state)

            await self._verify(spec, quant, directory, job)
            (directory / ".verified.json").write_text(
                _marker_payload(spec, quant, directory), encoding="utf-8"
            )
            status = self.status(spec, quant.name if quant else None)
            self._record_installation(spec, quant, status)
            await self.bus.update_job(
                job, status="done", progress=1.0, message=f"{spec.name} listo", result=status.to_dict()
            )
            return {"model": status.to_dict(), "alreadyInstalled": False}
        except DownloadCancelled:
            await self.bus.update_job(job, status="cancelled", message=f"Descarga de {spec.name} cancelada")
            return {"model": self.status(spec, quant.name if quant else None).to_dict(), "cancelled": True}
        except Exception as exc:  # pragma: no cover - camino de error de red
            logger.warning("Fallo la descarga de %s: %s", spec.id, exc)
            await self.bus.update_job(job, status="error", message=str(exc), error=str(exc))
            raise
        finally:
            self._states.pop(spec.id, None)

    async def _download_llm(self, spec: ModelSpec, quant: Any, directory: Path, job: Job, state: DownloadState) -> None:
        target = directory / quant.file
        if target.exists() and target.stat().st_size == quant.bytes:
            await self.bus.update_job(job, progress=0.98, message="Archivo ya presente; verificando")
            return
        await self._stream_download(
            f"https://huggingface.co/{spec.repo}/resolve/{spec.revision}/{quant.file}",
            target,
            total=quant.bytes,
            job=job,
            state=state,
        )

    async def _download_repo(self, spec: ModelSpec, directory: Path, job: Job, state: DownloadState) -> None:
        try:  # pragma: no cover - depende de huggingface_hub
            from huggingface_hub import snapshot_download

            await self.bus.update_job(job, progress=0.05, message="Descargando con cache de Hugging Face")
            snapshot_download(
                repo_id=spec.repo,
                revision=spec.revision,
                local_dir=str(directory),
                allow_patterns=spec.allow_patterns or None,
                max_workers=4,
            )
            await self.bus.update_job(job, progress=0.95, message="Descarga completa; verificando")
            return
        except ImportError:  # pragma: no cover
            logger.info("huggingface_hub no disponible; se usa HTTP por rangos")
        except Exception as exc:  # pragma: no cover
            logger.warning("snapshot_download falló (%s); se reintenta por HTTP", exc)

        for index, file in enumerate(spec.files):
            url = f"https://huggingface.co/{spec.repo}/resolve/{spec.revision}/{file.path}"
            fraction = (index + 1) / max(1, len(spec.files))
            await self._stream_download(
                url,
                directory / file.path,
                total=file.bytes or spec.approx_bytes,
                job=job,
                state=state,
                progress_base=(index / max(1, len(spec.files))),
                progress_span=(1 / max(1, len(spec.files))),
            )
            _ = fraction

    async def _stream_download(
        self,
        url: str,
        target: Path,
        *,
        total: int,
        job: Job,
        state: DownloadState,
        progress_base: float = 0.0,
        progress_span: float = 0.98,
    ) -> None:
        import httpx

        partial = target.with_suffix(target.suffix + ".part")
        already = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={already}-"} if already else {}
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=30.0)
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            if response.status_code not in (200, 206):  # pragma: no cover
                raise RuntimeError(f"HTTP {response.status_code} al descargar {url}")
            content_length = int(response.headers.get("content-length", 0))
            expected = already + content_length if content_length else total
            mode = "ab" if response.status_code == 206 else "wb"
            if mode == "wb":
                already = 0
            written = already
            with partial.open(mode) as handle:
                async for block in response.aiter_bytes(CHUNK):
                    if state.cancelled:
                        raise DownloadCancelled()
                    handle.write(block)
                    written += len(block)
                    if expected:
                        await self.bus.update_job(
                            job,
                            progress=progress_base + progress_span * (written / expected),
                            message=f"{written // (1024 * 1024)} / {expected // (1024 * 1024)} MB",
                        )
        partial.replace(target)

    async def _verify(self, spec: ModelSpec, quant: Any, directory: Path, job: Job) -> None:
        from . import sha256_file

        await self.bus.update_job(job, progress=0.98, message="Verificando archivos")
        checks: list[tuple[Path, str, int]] = []
        if quant is not None:
            checks.append((directory / quant.file, quant.sha256, quant.bytes))
        else:
            for file in spec.files:
                if file.sha256 and file.bytes:
                    checks.append((directory / file.path, file.sha256, file.bytes))
        for path, expected_hash, expected_size in checks:
            if not path.exists():
                raise RuntimeError(f"Falta el archivo esperado {path.name}")
            actual_size = path.stat().st_size
            if expected_size and actual_size != expected_size:
                raise RuntimeError(
                    f"Tamaño incorrecto en {path.name}: {actual_size} != {expected_size}"
                )
            actual_hash = sha256_file(path)
            if expected_hash and actual_hash != expected_hash:
                raise RuntimeError(f"Hash incorrecto en {path.name}")
        await self.bus.update_job(job, progress=0.99, message="Archivos verificados")

    def _record_installation(self, spec: ModelSpec, quant: Any, status: ModelStatus) -> None:
        from ..db.repo import Repository
        from ..db.sqlite import Database

        db = Database(self.settings.db_path)
        try:
            db.migrate()
            repo = Repository(db)
            repo.db.insert_model_installation(
                model_id=spec.id,
                revision=spec.revision,
                quantization=quant.name if quant else None,
                path=status.path or "",
                size_bytes=status.size_bytes,
                sha256=quant.sha256 if quant else next((f.sha256 for f in spec.files if f.sha256), None),
                status="installed",
            )
        finally:
            db.close()

    # -- runtime llama.cpp ------------------------------------------------
    def _server_binary(self, runtime_id: str) -> Path | None:
        """Ubica ``llama-server`` dentro del runtime instalado.

        Los archivos de llama.cpp varían: ``build/bin/llama-server`` en algunas
        builds y ``llama-b<build>/llama-server`` en las de macOS.
        """
        base = self.settings.binary_dir / runtime_id
        if not base.exists():
            return None
        for candidate in sorted(base.rglob("llama-server")):
            if candidate.is_file():
                return candidate
        return None

    def runtime_status(self, target: str) -> dict[str, Any]:
        runtime = self.manifest.runtime["llamaCpp"]
        binary = self._server_binary(runtime.id)
        asset = runtime.assets.get(target)
        return {
            "id": runtime.id,
            "name": runtime.name,
            "license": runtime.license,
            "build": runtime.build,
            "minimumBuild": runtime.minimum_build,
            "target": target,
            "installed": binary is not None,
            "path": str(binary) if binary else None,
            "asset": asset.name if asset else None,
            "approxBytes": asset.bytes if asset else None,
        }

    async def download_runtime(self, target: str, job: Job | None = None) -> dict[str, Any]:
        runtime = self.manifest.runtime["llamaCpp"]
        asset = runtime.assets.get(target)
        if asset is None:
            raise RuntimeError(f"No hay runtime de llama.cpp para el target {target}")
        if self._server_binary(runtime.id) is not None:
            return self.runtime_status(target)
        base = self.settings.binary_dir / runtime.id
        archive = base / asset.name
        archive.parent.mkdir(parents=True, exist_ok=True)
        state = DownloadState()
        job = job or await self.bus.create_job("runtime_download", {"target": target})
        await self.bus.update_job(job, status="running", progress=0.0, message="Descargando llama.cpp")
        url = f"https://github.com/{runtime.repo}/releases/download/{runtime.build}/{asset.name}"
        await self._stream_download(url, archive, total=asset.bytes, job=job, state=state)
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract(tar, base)
        binary = self._server_binary(runtime.id)
        if binary is not None:
            binary.chmod(binary.stat().st_mode | 0o111)
        await self.bus.update_job(job, status="done", progress=1.0, message="llama.cpp listo")
        return self.runtime_status(target)


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    """Extrae evitando path traversal."""
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = (destination / member.name).resolve()
        if not str(member_path).startswith(str(destination)):
            raise RuntimeError(f"Entrada insegura en el archivo: {member.name}")
    tar.extractall(destination)


def _marker_payload(spec: ModelSpec, quant: Any, directory: Path) -> str:
    import json

    files = {}
    for path in directory.rglob("*"):
        if path.is_file() and path.name != ".verified.json":
            files[str(path.relative_to(directory))] = path.stat().st_size
    return json.dumps(
        {
            "modelId": spec.id,
            "revision": spec.revision,
            "quantization": quant.name if quant else None,
            "files": files,
        },
        indent=2,
    )
