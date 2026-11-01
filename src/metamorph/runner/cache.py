"""On-disk SQLite cache, so re-running an identical config costs nothing.

Two namespaces share one file: `target` (app responses) and `llm` (helper-model calls for LLM
transforms and judges). Target keys combine the target fingerprint, the canonical input, the
sample index and (optionally) the code version; including the sample index keeps the k
self-variance samples distinct yet reproducible. Failed calls are never cached.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from metamorph.types import Input
from metamorph.util import canonical_json, sha256

Namespace = Literal["target", "llm"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    namespace  TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (namespace, key)
)
"""


def cache_key(namespace: str, payload: Input, sample_idx: int) -> str:
    return sha256(namespace, canonical_json(payload), str(sample_idx))


class Cache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(_SCHEMA)
        self.db.commit()

    def get(self, namespace: Namespace, key: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT value FROM entries WHERE namespace=? AND key=?", (namespace, key)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, namespace: Namespace, key: str, value: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?)",
            (namespace, key, json.dumps(value, ensure_ascii=False), time.time()),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
