"""Scripted fakes (target and helper LLM) for testing without network calls."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable

from metamorph.adapters.base import Target, TargetResponse
from metamorph.llm.base import LLMProvider, LLMRequest, LLMResult
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


class ScriptedLLM(LLMProvider):
    """A helper-LLM fake: `script(request) -> str | Exception`; records every request."""

    def __init__(self, script: Callable[[LLMRequest], str | Exception], cost: float = 0.0) -> None:
        self.model = "scripted-llm"
        self.script = script
        self.cost = cost
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        result = self.script(request)
        if isinstance(result, Exception):
            raise result
        return LLMResult(text=result, model=self.model, cost_usd=self.cost)


def rewrites(mapping: Callable[[str], str]) -> Callable[[LLMRequest], str]:
    """Script that answers rewrite requests with mapping(input_text) as structured JSON."""

    def script(request: LLMRequest) -> str:
        text = request.prompt.split("<<<\n", 1)[1].split("\n>>>", 1)[0]
        return json.dumps({"rewritten": mapping(text)})

    return script
