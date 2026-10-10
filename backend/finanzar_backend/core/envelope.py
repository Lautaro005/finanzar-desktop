"""Envelope uniforme para todas las respuestas HTTP.

Forma acordada::

    {"ok": true, "data": {...}, "error": null, "request_id": "local-uuid"}
    {"ok": false, "data": null, "error": {...}, "request_id": "local-uuid"}
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from .ids import request_id as new_request_id


def ok(data: Any = None, *, request_id: str | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": True,
            "data": data,
            "error": None,
            "request_id": request_id or new_request_id(),
        },
    )


def fail(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    status_code: int = 400,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message, "details": details or {}},
            "request_id": request_id or new_request_id(),
        },
    )
