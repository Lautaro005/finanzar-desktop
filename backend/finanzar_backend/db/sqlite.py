"""Capa SQLite: conexión, migraciones y helpers transaccionales.

SQLite es la fuente de verdad estructurada de FinanzAR. Se habilita WAL y
claves foráneas, y se aplican migraciones numeradas desde ``db/migrations``.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _make_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class Database:
    """Envoltorio fino sobre ``sqlite3`` con migraciones y lock de escritura.

    SQLite en modo WAL admite lecturas concurrentes; un ``threading.Lock``
    serializa las escrituras para evitar ``database is locked`` bajo uvicorn.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn = _make_connection(self.path)
        self._write_lock = threading.RLock()

    # -- ciclo de vida ----------------------------------------------------
    def close(self) -> None:
        with self._write_lock:
            self._conn.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # -- migraciones ------------------------------------------------------
    def migrate(self) -> list[str]:
        applied: list[str] = []
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {row[0] for row in self._conn.execute("SELECT version FROM schema_migrations")}
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = sql_file.stem
            if version in done:
                continue
            script = sql_file.read_text(encoding="utf-8")
            with self._write_lock:
                self._conn.executescript(script)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, utcnow()),
                )
            applied.append(version)
        return applied

    def schema_version(self) -> str | None:
        try:
            row = self._conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None

    # -- helpers ----------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._write_lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        with self._write_lock:
            self._conn.executemany(sql, seq)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params))

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, params).fetchone()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def upsert_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, utcnow()),
        )

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM app_settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def insert_model_installation(
        self,
        *,
        model_id: str,
        revision: str,
        quantization: str | None,
        path: str,
        size_bytes: int,
        sha256: str | None,
        status: str = "installed",
    ) -> None:
        now = utcnow()
        self.execute(
            "INSERT INTO model_installations "
            "(id, model_id, revision, quantization, path, size_bytes, sha256, status, installed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(model_id, revision, quantization) DO UPDATE SET "
            "path=excluded.path, size_bytes=excluded.size_bytes, sha256=excluded.sha256, "
            "status=excluded.status, installed_at=excluded.installed_at, updated_at=excluded.updated_at",
            (
                f"{model_id}:{revision}:{quantization}",
                model_id,
                revision,
                quantization,
                path,
                size_bytes,
                sha256,
                status,
                now,
                now,
            ),
        )

    def get_model_installation(
        self, model_id: str, revision: str, quantization: str | None = None
    ) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM model_installations WHERE model_id = ? AND revision = ? "
            "AND COALESCE(quantization, '') = COALESCE(?, '')",
            (model_id, revision, quantization),
        )
