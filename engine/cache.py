"""SQLite cache with a per-source TTL. Stores raw registry JSON, never secrets."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("CACHE_PATH", "./.cache/installgate.sqlite"))

TTL_SECONDS: dict[str, int] = {
    "pypi": 3600,
    "npm": 3600,
    "osv": 900,
    "huggingface": 3600,
    "docker_registry": 3600,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    source TEXT NOT NULL,
    key    TEXT NOT NULL,
    body   TEXT NOT NULL,
    stored_at REAL NOT NULL,
    PRIMARY KEY (source, key)
)
"""


class Cache:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, source: str, key: str) -> Any | None:
        ttl = TTL_SECONDS.get(source, 900)
        row = self._conn.execute(
            "SELECT body, stored_at FROM entries WHERE source = ? AND key = ?",
            (source, key),
        ).fetchone()
        if row is None:
            return None
        body, stored_at = row
        if time.time() - stored_at > ttl:
            self._conn.execute("DELETE FROM entries WHERE source = ? AND key = ?", (source, key))
            self._conn.commit()
            return None
        return json.loads(body)

    def set(self, source: str, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO entries (source, key, body, stored_at) VALUES (?, ?, ?, ?)",
            (source, key, json.dumps(value), time.time()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
