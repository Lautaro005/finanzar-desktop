"""Errores de dominio con envelope consistente.

Todo error devuelve ``code`` (estable, para la interfaz), ``message`` (legible
para la persona) y ``details`` (diagnóstico local, nunca datos sensibles).
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = dict(details) if details is not None else {}
        if status_code is not None:
            self.status_code = status_code

    def to_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ValidationError(ApiError):
    status_code = 422
    code = "validation_error"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class ModelUnavailableError(ApiError):
    status_code = 503
    code = "model_unavailable"


class PermissionDeniedError(ApiError):
    status_code = 403
    code = "permission_denied"


class PathNotAllowedError(ApiError):
    status_code = 403
    code = "path_not_allowed"
