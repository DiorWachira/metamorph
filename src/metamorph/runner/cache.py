"""On-disk SQLite cache of target responses, so re-running an identical config costs nothing.

Keys combine the target fingerprint, the canonical input, the sample index and (optionally) the
code version. Including the sample index keeps the k self-variance samples distinct yet
reproducible. Failed calls are never cached.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from metamorph.adapters.base import TargetResponse
from metamorph.types import Input
from metamorph.util import canonical_json, sha256

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key        TEXT PRIMARY KEY,
    text       TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    tokens_in  INTEGER,
    tokens_out INTEGER,
    cost_usd   REAL NOT NULL,
    created_at REAL NOT NULL
)
"""


def cache_key(namespace: str, payload: Input, sample_idx: int) -> str:
    return sha256(namespace, canonical_json(payload), str(sample_idx))


class ResponseCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(_SCHEMA)
        self.db.commit()

    def get(self, key: str) -> tuple[TargetResponse, float] | None:
        row = self.db.execute(
            "SELECT text, latency_ms, tokens_in, tokens_out, cost_usd FROM responses WHERE key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        text, latency_ms, tokens_in, tokens_out, cost = row
        return TargetResponse(text, tokens_in, tokens_out, cost), latency_ms

    def put(self, key: str, response: TargetResponse, latency_ms: float) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                response.text,
                latency_ms,
                response.tokens_in,
                response.tokens_out,
                response.cost_usd,
                time.time(),
            ),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
