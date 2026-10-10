"""Identificadores locales y request ids."""

from __future__ import annotations

import uuid


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value


def request_id() -> str:
    return f"local-{uuid.uuid4()}"
