"""Bus de eventos de progreso y registro de trabajos en proceso.

Los trabajos largos (descarga de modelos, OCR, export, indexado) publican
progreso por SSE hacia Rust y la interfaz. Sin dependencias externas: se usan
colas ``asyncio`` por suscriptor.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .ids import new_id


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | error | cancelled
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "meta": self.meta,
        }


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    # -- trabajos ---------------------------------------------------------
    async def create_job(self, kind: str, meta: dict[str, Any] | None = None) -> Job:
        job = Job(id=new_id("job"), kind=kind, meta=meta or {})
        async with self._lock:
            self._jobs[job.id] = job
        await self.publish({"type": "job.created", "job": job.to_dict()})
        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, kind: str | None = None) -> list[Job]:
        jobs = list(self._jobs.values())
        if kind is not None:
            jobs = [j for j in jobs if j.kind == kind]
        return jobs

    async def update_job(
        self,
        job: Job,
        *,
        status: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if message is not None:
            job.message = message
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        await self.publish({"type": "job.updated", "job": job.to_dict()})

    # -- suscripción SSE --------------------------------------------------
    async def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


bus = EventBus()
