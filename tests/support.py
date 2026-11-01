"""Shared test support: seed fixtures and a config builder for suite-level tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metamorph.config import Config

SEEDS = [
    {"id": f"s{i}", "input": {"question": f"Which county does question number {i} concern?"}}
    for i in range(5)
]


def make_config(tmp_path: Path, **overrides: Any) -> Config:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "seeds.jsonl").write_text(
        "\n".join(json.dumps(s) for s in overrides.pop("seeds", SEEDS)), encoding="utf-8"
    )
    raw: dict[str, Any] = {
        "target": {"type": "python", "callable": "unused:fn"},
        "seeds": "seeds.jsonl",
        "fields": {"text": "question"},
        "relations": [{"id": "typo-robustness", "mode": "blocking"}],
        "run": {"backoff_s": 0},
        **overrides,
    }
    cfg = Config.model_validate(raw)
    cfg.base_dir = tmp_path
    cfg.snapshot = raw
    return cfg
