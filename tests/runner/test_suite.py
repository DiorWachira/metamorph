"""Runner behaviour against a scripted target: cache, retries, errors, gate, self-variance."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import pytest
from fakes import ScriptedTarget

from metamorph.adapters.base import Target, TargetResponse
from metamorph.config import Config
from metamorph.errors import RetryableTargetError, TargetError
from metamorph.suite import RunOptions, run_suite
from metamorph.types import Input, Status

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


def constant(answer: str = "Nairobi county"):  # type: ignore[no-untyped-def]
    return lambda payload, n: answer


async def test_rerun_is_served_from_cache_with_identical_verdicts(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    target = ScriptedTarget(lambda p, n: p["question"].upper(), cost_per_call=0.01)
    first = await run_suite(cfg, target=target)
    calls_after_first = target.total_calls
    assert calls_after_first == 10  # 5 sources + 5 follow-ups
    assert first.run.total_cost_usd == pytest.approx(0.10)

    second = await run_suite(cfg, target=target)
    assert target.total_calls == calls_after_first
    assert second.run.stats["cache_hits"] == second.run.stats["requested"] == 10
    assert second.run.total_cost_usd == 0.0
    assert [(c.seed_id, c.status, c.score) for c in second.cases] == [
        (c.seed_id, c.status, c.score) for c in first.cases
    ]
    assert all(o.cached for c in second.cases for o in c.source_outputs)


async def test_no_cache_option_calls_again(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    target = ScriptedTarget(constant())
    await run_suite(cfg, target=target)
    await run_suite(cfg, RunOptions(use_cache=False), target=target)
    assert target.total_calls == 20


async def test_sources_are_shared_across_relations(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, relations=["typo-robustness", "distractor-invariance"])
    target = ScriptedTarget(constant())
    report = await run_suite(cfg, target=target)
    assert len(report.cases) == 10
    assert target.total_calls == 15  # 5 shared sources + 10 follow-ups


async def test_retries_transient_failures(tmp_path: Path) -> None:
    def flaky(payload: Input, n: int) -> str | Exception:
        return RetryableTargetError("503") if n < 2 else "ok"

    report = await run_suite(make_config(tmp_path), target=ScriptedTarget(flaky))
    assert all(c.status is Status.PASS for c in report.cases)
    assert report.run.stats["target_calls"] == 30


async def test_gives_up_and_records_errors(tmp_path: Path) -> None:
    target = ScriptedTarget(lambda p, n: RetryableTargetError("503"))
    report = await run_suite(
        make_config(tmp_path, run={"backoff_s": 0, "retries": 2}), target=target
    )
    assert all(c.status is Status.ERROR for c in report.cases)
    assert "gave up after 3 attempts" in report.cases[0].detail
    assert report.gate is not None and report.gate.too_many_errors


async def test_permanent_errors_are_not_retried(tmp_path: Path) -> None:
    target = ScriptedTarget(lambda p, n: TargetError("400 bad request"))
    report = await run_suite(make_config(tmp_path), target=target)
    assert target.total_calls == 10
    assert report.run.stats["errors"] == 10


async def test_errors_are_never_cached(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    await run_suite(cfg, target=ScriptedTarget(lambda p, n: TargetError("down")))
    healed = ScriptedTarget(constant())
    report = await run_suite(cfg, target=healed)
    assert healed.total_calls == 10 and all(c.status is Status.PASS for c in report.cases)


async def test_gate_counts_only_blocking_violations(tmp_path: Path) -> None:
    originals = {s["input"]["question"] for s in SEEDS}

    def unstable(payload: Input, n: int) -> str:
        return "Nairobi" if payload["question"] in originals else "Kisumu"

    blocking = await run_suite(make_config(tmp_path / "a"), target=ScriptedTarget(unstable))
    assert blocking.gate is not None and not blocking.gate.passed
    assert blocking.gate.blocking_violations == len(blocking.violations) == 5

    warning_cfg = make_config(tmp_path / "b", relations=["typo-robustness"])
    warning = await run_suite(warning_cfg, target=ScriptedTarget(unstable))
    assert warning.violations and warning.gate is not None and warning.gate.passed


async def test_skips_are_reported(tmp_path: Path) -> None:
    seeds = [{"id": "a", "tags": ["rag"], "input": {"question": "Is it far?"}}]
    relations = ["typo-robustness", "doc-order-invariance"]
    cfg = make_config(tmp_path, seeds=seeds, relations=relations)
    report = await run_suite(cfg, target=ScriptedTarget(constant()))
    reasons = {s.relation_id: s.reason for s in report.skipped}
    assert "nothing to change" in reasons["typo-robustness"]
    assert "documents" in reasons["doc-order-invariance"]
    assert report.cases == []


async def test_concurrency_limit(tmp_path: Path) -> None:
    class Slow(Target):
        in_flight = peak = 0

        @property
        def fingerprint(self) -> str:
            return "slow"

        async def call(self, payload: Input) -> TargetResponse:
            Slow.in_flight += 1
            Slow.peak = max(Slow.peak, Slow.in_flight)
            await asyncio.sleep(0.01)
            Slow.in_flight -= 1
            return TargetResponse("x")

    cfg = make_config(tmp_path, run={"concurrency": 2, "backoff_s": 0})
    await run_suite(cfg, target=Slow())
    assert Slow.peak == 2


async def test_self_variance_cuts_false_violations_on_a_noisy_target(tmp_path: Path) -> None:
    """A target that rephrases randomly is not broken by typos; the baseline should see that."""
    vocab = ["Nairobi", "county", "is", "the", "answer", "likely", "probably", "here"]

    def noisy(payload: Input, n: int) -> str:
        rng = random.Random(f"{payload['question']}|{n}")
        return " ".join(rng.sample(vocab, 5))

    seeds = [
        {"id": f"s{i}", "input": {"question": f"Which county is number {i} in?"}} for i in range(30)
    ]
    naive = await run_suite(make_config(tmp_path / "k1", seeds=seeds), target=ScriptedTarget(noisy))
    baseline_cfg = make_config(tmp_path / "k3", seeds=seeds, run={"samples": 3, "backoff_s": 0})
    baselined = await run_suite(baseline_cfg, target=ScriptedTarget(noisy))
    assert len(baselined.violations) < len(naive.violations)
    assert all(c.self_variance is not None for c in baselined.cases)
