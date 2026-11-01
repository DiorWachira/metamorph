"""Calls the target with a concurrency limit, retries with backoff, the cache and the budget."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from metamorph.adapters.base import Target, TargetResponse
from metamorph.errors import RetryableTargetError, TargetError
from metamorph.runner.budget import Budget, BudgetExhausted
from metamorph.runner.cache import Cache, cache_key
from metamorph.types import Input, TargetOutput

MAX_BACKOFF_S = 30.0


@dataclass
class CallStats:
    requested: int = 0
    cache_hits: int = 0
    target_calls: int = 0  # attempts actually sent, retries included
    errors: int = 0
    skipped: int = 0  # not called because the budget ran out
    cost_usd: float = 0.0


class CallExecutor:
    def __init__(
        self,
        target: Target,
        cache: Cache | None,
        namespace: str,
        concurrency: int = 8,
        retries: int = 3,
        backoff_s: float = 0.5,
        on_done: Callable[[], None] | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.target = target
        self.cache = cache
        self.budget = budget or Budget()
        self.namespace = namespace
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries
        self.backoff_s = backoff_s
        self.on_done = on_done
        self.stats = CallStats()
        self._jitter = random.Random()

    async def get(self, payload: Input, sample_idx: int) -> TargetOutput:
        self.stats.requested += 1
        try:
            return await self._get(payload, sample_idx)
        finally:
            if self.on_done:
                self.on_done()

    async def _get(self, payload: Input, sample_idx: int) -> TargetOutput:
        key = cache_key(self.namespace, payload, sample_idx)
        if self.cache and (hit := self.cache.get("target", key)):
            self.stats.cache_hits += 1
            # A cached response costs nothing in this run.
            return TargetOutput(
                hit["text"], hit["latency_ms"], hit["tokens_in"], hit["tokens_out"], 0.0, True
            )

        async with self.semaphore:
            try:
                self.budget.check()  # inside the semaphore: queued calls see the latest spend
            except BudgetExhausted as exc:
                self.stats.skipped += 1
                return TargetOutput("", 0.0, error=str(exc), skipped=True)
            started = time.perf_counter()
            try:
                response = await self._call_with_retries(payload)
            except TargetError as exc:
                self.stats.errors += 1
                latency = (time.perf_counter() - started) * 1000
                return TargetOutput("", latency, error=str(exc))
            latency = (time.perf_counter() - started) * 1000

        self.stats.cost_usd += response.cost_usd
        self.budget.charge(response.cost_usd)
        if self.cache:
            self.cache.put(
                "target",
                key,
                {
                    "text": response.text,
                    "latency_ms": latency,
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                },
            )
        return TargetOutput(
            response.text, latency, response.tokens_in, response.tokens_out, response.cost_usd
        )

    async def _call_with_retries(self, payload: Input) -> TargetResponse:
        for attempt in range(self.retries + 1):
            self.stats.target_calls += 1
            try:
                return await self.target.call(payload)
            except RetryableTargetError as exc:
                if attempt == self.retries:
                    raise TargetError(f"{exc} (gave up after {attempt + 1} attempts)") from exc
                await asyncio.sleep(self._delay(attempt, exc.retry_after))
        raise AssertionError("unreachable")

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        backoff = self.backoff_s * 2.0**attempt + self._jitter.uniform(0, self.backoff_s)
        return min(MAX_BACKOFF_S, max(backoff, retry_after or 0.0))
