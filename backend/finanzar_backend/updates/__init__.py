"""Comprobación de actualizaciones contra GitHub Releases.

Nunca instala nada: informa la versión disponible y su changelog, y deja la
instalación firmada al updater de Tauri, siempre con consentimiento explícito.
Soporta modo offline (devuelve el último estado conocido).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings
from ..db.sqlite import utcnow
from ..llm.llama_server import current_target

logger = logging.getLogger(__name__)

SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.search(value or "")
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str | None
    available: bool
    channel: str
    target: str
    published_at: str | None
    notes: str | None
    asset: dict[str, Any] | None
    checked_at: str
    offline: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "currentVersion": self.current_version,
            "latestVersion": self.latest_version,
            "available": self.available,
            "channel": self.channel,
            "target": self.target,
            "publishedAt": self.published_at,
            "notes": self.notes,
            "asset": self.asset,
            "checkedAt": self.checked_at,
            "offline": self.offline,
            "error": self.error,
            "requiresConsent": True,
        }


def _pick_asset(assets: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    arch = "aarch64" if target.startswith("aarch64") else "x86_64"
    for asset in assets:
        name = asset.get("name", "").lower()
        if arch in name and ("dmg" in name or "app.tar.gz" in name or "tar.gz" in name):
            return {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url"),
                "bytes": asset.get("size"),
                "signature": asset.get("name", "").endswith(".sig"),
            }
    return None


class UpdateChecker:
    def __init__(self, settings: Settings, current_version: str) -> None:
        self.settings = settings
        self.current_version = current_version
        self.channel = "stable"

    def check(self, timeout: float = 20.0) -> UpdateInfo:
        target = current_target()
        url = f"https://api.github.com/repos/{self.settings.update_repo}/releases/latest"
        try:
            response = httpx.get(
                url,
                timeout=timeout,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "FinanzAR-Desktop"},
            )
            if response.status_code == 404:
                return UpdateInfo(
                    current_version=self.current_version,
                    latest_version=None,
                    available=False,
                    channel=self.channel,
                    target=target,
                    published_at=None,
                    notes=None,
                    asset=None,
                    checked_at=utcnow(),
                    error="Sin releases publicadas todavía",
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - red
            logger.warning("No se pudo consultar actualizaciones: %s", exc)
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=None,
                available=False,
                channel=self.channel,
                target=target,
                published_at=None,
                notes=None,
                asset=None,
                checked_at=utcnow(),
                offline=True,
                error=str(exc),
            )
        latest = str(payload.get("tag_name", "")).lstrip("v")
        assets = payload.get("assets", []) or []
        return UpdateInfo(
            current_version=self.current_version,
            latest_version=latest or None,
            available=bool(latest) and is_newer(latest, self.current_version),
            channel=self.channel,
            target=target,
            published_at=payload.get("published_at"),
            notes=payload.get("body"),
            asset=_pick_asset(assets, target),
            checked_at=utcnow(),
        )
