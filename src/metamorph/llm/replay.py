"""Record/replay of helper-LLM calls, so LLM relations run in CI with no key and no cost.

Record once against a real model (`llm.record_to: recordings.jsonl`), commit the file, then run
with `llm.provider: replay`. Requests are matched by their fingerprint (system + prompt + schema),
so a changed prompt is a loud miss rather than a silently stale answer.
"""

from __future__ import annotations

import json
from pathlib import Path

from metamorph.errors import ConfigError
from metamorph.llm.base import LLMError, LLMProvider, LLMRequest, LLMResult


def recording_line(request: LLMRequest, result: LLMResult, purpose: str) -> str:
    return json.dumps(
        {
            "key": request.fingerprint(),
            "purpose": purpose,
            "model": result.model,
            "prompt": request.prompt[:200],
            "response": result.text,
        },
        ensure_ascii=False,
    )


class ReplayProvider(LLMProvider):
    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise ConfigError(f"llm recordings not found: {path}")
        self.model = "replay"
        self.responses: dict[str, tuple[str, str]] = {}
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                self.responses[row["key"]] = (row["response"], row.get("model", "replay"))
            except (json.JSONDecodeError, KeyError) as exc:
                raise ConfigError(f"{path}:{n}: invalid recording ({exc})") from exc

    async def complete(self, request: LLMRequest) -> LLMResult:
        hit = self.responses.get(request.fingerprint())
        if hit is None:
            raise LLMError(f"no recording for this request: {request.prompt[:80]!r}...")
        text, model = hit
        return LLMResult(text=text, model=f"replay:{model}")
