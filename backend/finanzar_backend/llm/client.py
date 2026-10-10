"""Cliente OpenAI-compatible contra ``llama-server`` local."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    content: str
    model: str
    usage: dict[str, Any] | None = None


class LlamaClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=2.0).status_code == 200
        except Exception:
            return False

    def available(self) -> bool:
        return self.health()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            # Spark-X2.5 es un modelo de razonamiento: sin esto consume todos los
            # tokens en `reasoning_content` y deja `content` vacío.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": json_schema}
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return ChatResult(
            content=str(message.get("content", "")).strip(),
            model=str(data.get("model", "spark")),
            usage=data.get("usage"),
        )
