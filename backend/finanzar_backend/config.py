"""Configuración del backend local.

Todos los valores tienen un default seguro y local-first. El directorio de datos
vive dentro de ``~/Library/Application Support/FinanzAR`` en macOS salvo que se
sobreescriba con ``FINANZAR_DATA_DIR``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR_NAME = "FinanzAR"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def default_data_dir() -> Path:
    override = os.environ.get("FINANZAR_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    home = Path.home()
    return home / "Library" / "Application Support" / APP_DIR_NAME


def repo_root() -> Path:
    """Raíz del repositorio/proyecto empaquetado.

    Se resuelve subiendo desde este archivo. En builds PyInstaller el manifest
    se copia junto al ejecutable y ``models/manifest.json`` se busca ahí.
    """
    env = os.environ.get("FINANZAR_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "models" / "manifest.json").exists():
            return parent
    # PyInstaller: el manifest viaja al lado del binario.
    return Path(getattr(__import__("sys"), "_MEIPASS", here.parent))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINANZAR_", extra="ignore")

    host: str = HOST
    port: int = DEFAULT_PORT
    data_dir: Path = Field(default_factory=default_data_dir)
    log_level: str = "INFO"

    # Repositorios de modelos (fijados por revisión en models/manifest.json).
    hf_endpoint: str = "https://huggingface.co"
    llm_context_size: int = 8192
    llm_threads: int = 0  # 0 = automático

    # Updater
    update_repo: str = "finanzar/finanzar-local"
    update_check_interval_seconds: int = 3 * 60 * 60

    @property
    def db_path(self) -> Path:
        return self.data_dir / "finanzar.sqlite3"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def binary_dir(self) -> Path:
        """Directorio de runtimes empaquetados (llama-server)."""
        return self.data_dir / "bin"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.chroma_path,
            self.documents_dir,
            self.models_dir,
            self.backups_dir,
            self.logs_dir,
            self.binary_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
