"""Small helpers shared across the package: hashing, dotted field paths, env expansion."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
from typing import Any

from metamorph.errors import ConfigError

_MISSING = object()


def canonical_json(value: Any) -> str:
    """Stable JSON encoding: sorted keys, no whitespace, unicode kept as-is."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def derive_rng(*parts: object) -> random.Random:
    """A Random seeded from arbitrary parts, so the same parts always give the same stream."""
    seed = int(sha256(*(str(p) for p in parts))[:16], 16)
    return random.Random(seed)


def _split(path: str) -> list[str | int]:
    return [int(p) if p.isdigit() else p for p in path.split(".")]


def get_path(data: Any, path: str, default: Any = None) -> Any:
    """Read `a.b.0.c` from nested dicts/lists; returns `default` when any step is missing."""
    node = data
    for key in _split(path):
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return default
    return node


def has_path(data: Any, path: str) -> bool:
    return get_path(data, path, _MISSING) is not _MISSING


def with_path(data: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep copy of `data` with `path` set to `value`. The path must already exist."""
    result = copy.deepcopy(data)
    keys = _split(path)
    node: Any = result
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    return result


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: Any) -> Any:
    """Recursively replace `${VAR}` in strings with environment values. Missing vars are errors."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ConfigError(f"environment variable {name} is not set")
            return os.environ[name]

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def output_to_text(value: Any) -> str:
    """Normalise whatever a target returned into the text we compare and store."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
