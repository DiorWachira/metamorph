"""A scripted target for testing the runner without network calls."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from metamorph.adapters.base import Target, TargetResponse
from metamorph.types import Input
from metamorph.util import canonical_json

Script = Callable[[Input, int], str | Exception]


class ScriptedTarget(Target):
    """Responds via `script(payload, nth_call_for_this_payload)`; returned exceptions are raised."""

    def __init__(self, script: Script, cost_per_call: float = 0.0) -> None:
        self.script = script
        self.cost_per_call = cost_per_call
        self.calls: Counter[str] = Counter()

    @property
    def fingerprint(self) -> str:
        return "scripted"

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    async def call(self, payload: Input) -> TargetResponse:
        key = canonical_json(payload)
        n = self.calls[key]
        self.calls[key] += 1
        result = self.script(payload, n)
        if isinstance(result, Exception):
            raise result
        return TargetResponse(text=result, cost_usd=self.cost_per_call)
