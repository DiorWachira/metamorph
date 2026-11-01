"""Seed files: JSONL, one source input per line.

    {"id": "q1", "input": {"question": "..."}, "tags": ["rag", "en"]}

`id` and `tags` are optional; a missing id becomes `line-<n>`.
"""

from __future__ import annotations

import json
from pathlib import Path

from metamorph.errors import ConfigError
from metamorph.types import Seed


def load_seeds(path: Path, limit: int | None = None) -> list[Seed]:
    if not path.exists():
        raise ConfigError(f"seed file not found: {path}")
    seeds: list[Seed] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path}:{n}: invalid JSON ({exc.msg})") from exc
        if not isinstance(row, dict) or not isinstance(row.get("input"), dict):
            raise ConfigError(f'{path}:{n}: each line needs an "input" object')
        seed_id = str(row.get("id", f"line-{n}"))
        if seed_id in seen:
            raise ConfigError(f"{path}:{n}: duplicate seed id {seed_id!r}")
        seen.add(seed_id)
        tags = row.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ConfigError(f'{path}:{n}: "tags" must be a list of strings')
        seeds.append(Seed(id=seed_id, input=row["input"], tags=frozenset(tags)))
        if limit is not None and len(seeds) >= limit:
            break
    if not seeds:
        raise ConfigError(f"seed file is empty: {path}")
    return seeds
