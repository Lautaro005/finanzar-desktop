"""Descarga, verificación y arranque de modelos y runtimes locales."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1024 * 1024


def sha256_file(path: Path, *, cancel: object | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            if cancel is not None and getattr(cancel, "cancelled", False):  # pragma: no cover
                raise RuntimeError("cálculo de hash cancelado")
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
