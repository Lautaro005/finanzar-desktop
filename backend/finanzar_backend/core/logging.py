"""Logging estructurado con redacción de datos sensibles.

Nunca se registran imágenes, OCR completo, importes privados completos ni
prompts completos. Los números de tarjeta se enmascaran dejando marca y últimos
cuatro dígitos.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,19}\b")
_AMOUNT_RE = re.compile(r"(AR\$|US\$)\s?[\d.,]+")


def redact(text: str) -> str:
    text = _CARD_RE.sub(lambda m: mask_card(m.group(0)), text)
    text = _AMOUNT_RE.sub(lambda m: f"{m.group(1)} [redactado]", text)
    return text


def mask_card(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    if len(digits) < 4:
        return "****"
    return f"**** **** **** {digits[-4:]}"


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(_JsonFormatter())
    stream.addFilter(_RedactingFilter())
    root.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(_JsonFormatter())
        file_handler.addFilter(_RedactingFilter())
        root.addHandler(file_handler)

    # Silenciar ruido de librerías que pueden filtrar rutas locales.
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
