"""The helper-LLM service for transforms and comparators: cache, budget, concurrency, stats."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metamorph.llm.base import LLMError, LLMProvider, LLMRequest, LLMResult
from metamorph.llm.replay import recording_line
from metamorph.runner.budget import Budget
from metamorph.runner.cache import Cache
from metamorph.runner.pacing import RateLimiter


@dataclass
class LLMStats:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    cost_usd: float = 0.0


class LLMService:
    def __init__(
        self,
        provider: LLMProvider,
        cache: Cache | None = None,
        budget: Budget | None = None,
        concurrency: int = 4,
        record_to: Path | None = None,
        pace: RateLimiter | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.budget = budget or Budget()
        self.semaphore = asyncio.Semaphore(concurrency)
        self.record_to = record_to
        self.pace = pace
        self.stats = LLMStats()

    @property
    def model(self) -> str:
        return self.provider.model

    async def complete(self, purpose: str, request: LLMRequest) -> LLMResult:
        """Run a request, keyed for caching by (purpose, model, request)."""
        key = f"{purpose}|{self.model}|{request.fingerprint()}"
        if self.cache and (hit := self.cache.get("llm", key)):
            self.stats.cache_hits += 1
            return LLMResult(text=hit["text"], model=hit["model"])  # cached: free this run

        self.budget.check()
        async with self.semaphore:
            if self.pace:
                await self.pace.wait()
            try:
                result = await self.provider.complete(request)
            except LLMError:
                self.stats.failures += 1
                raise
        self.stats.calls += 1
        self.stats.cost_usd += result.cost_usd
        self.budget.charge(result.cost_usd)
        if self.cache:
            self.cache.put("llm", key, {"text": result.text, "model": result.model})
        if self.record_to:
            with self.record_to.open("a", encoding="utf-8") as f:
                f.write(recording_line(request, result, purpose) + "\n")
        return result

    async def complete_json(self, purpose: str, request: LLMRequest) -> dict[str, Any]:
        result = await self.complete(purpose, request)
        try:
            data = json.loads(result.text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"helper model returned invalid JSON: {result.text[:120]!r}") from exc
        if not isinstance(data, dict):
            raise LLMError("helper model returned JSON that is not an object")
        return data

    async def aclose(self) -> None:
        await self.provider.aclose()
