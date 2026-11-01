"""M2 runner behaviour: cost budget, LLM relations, baseline accounting, learned modes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fakes import ScriptedLLM, ScriptedTarget, rewrites
from test_suite import make_config

from metamorph.llm.base import LLMError
from metamorph.suite import RunOptions, open_store, run_suite
from metamorph.types import Mode, Status

QUESTIONS = [
    {"id": f"q{i}", "input": {"question": f"Which county is number {i} in Kenya?"}}
    for i in range(4)
]


async def test_budget_stops_gracefully(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, seeds=QUESTIONS, run={"backoff_s": 0, "concurrency": 1})
    target = ScriptedTarget(lambda p, n: "Nairobi", cost_per_call=0.01)
    report = await run_suite(cfg, RunOptions(budget_usd=0.025), target=target)

    assert report.run.status == "budget_exhausted"
    assert target.total_calls == 3  # 3 x $0.01 crosses the $0.025 line; nothing new starts
    statuses = {c.status for c in report.cases}
    assert Status.SKIPPED in statuses
    assert report.gate is not None and not report.gate.too_many_errors  # skipped is not error
    assert report.run.budget == {"limit_usd": 0.025, "spent_usd": 0.03}


async def test_llm_relation_end_to_end_with_cache(tmp_path: Path) -> None:
    relations = [
        {"id": "paraphrase-invariance", "comparator": {"name": "token_f1", "threshold": 0.8}}
    ]
    cfg = make_config(tmp_path, seeds=QUESTIONS, relations=relations)
    llm = ScriptedLLM(rewrites(lambda t: t.replace("Which county", "What county")), cost=0.002)

    def answer(payload: dict[str, Any], n: int) -> str:
        return "Kisumu" if payload["question"].startswith("What") else "Nairobi"

    report = await run_suite(cfg, target=ScriptedTarget(answer), llm_provider=llm)
    assert len(report.violations) == 4
    assert report.run.llm is not None and report.run.llm["calls"] == 4
    assert report.run.total_cost_usd == 4 * 0.002

    again = await run_suite(cfg, target=ScriptedTarget(answer), llm_provider=llm)
    assert len(llm.requests) == 4  # follow-ups came from the LLM cache
    assert again.run.total_cost_usd == 0.0
    assert [c.followup_input for c in again.cases] == [c.followup_input for c in report.cases]


async def test_llm_failures_become_skips(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, seeds=QUESTIONS, relations=["paraphrase-invariance"])
    llm = ScriptedLLM(lambda r: LLMError("helper declined"))
    report = await run_suite(cfg, target=ScriptedTarget(lambda p, n: "x"), llm_provider=llm)
    assert report.cases == []
    assert {s.reason for s in report.skipped} == {"transform failed: helper declined"}


async def test_baseline_accounting_and_unstable_inputs(tmp_path: Path) -> None:
    originals = {s["input"]["question"] for s in QUESTIONS}

    def noisy(payload: dict[str, Any], n: int) -> str:
        if payload["question"] in originals:  # source samples agree with each other at F1 0.5
            return ["alpha beta gamma delta", "alpha beta gamma omega", "alpha beta pi rho"][n % 3]
        return "alpha beta zeta eta"  # F1 0.5 vs the source: below 0.8, but within its noise

    cfg = make_config(tmp_path, seeds=QUESTIONS[:2], run={"samples": 3, "backoff_s": 0})
    report = await run_suite(cfg, target=ScriptedTarget(noisy))
    effect = report.baseline_effect
    assert effect["naive_violations"] == effect["violations"] + effect["excused"]
    assert effect["excused"] > 0
    assert {u.seed_id for u in report.unstable_inputs} == {"q0", "q1"}
    assert all(u.self_agreement < u.threshold for u in report.unstable_inputs)
    payload = json.loads(report.model_dump_json())
    assert "unstable_inputs" in payload and "baseline_effect" in payload


async def test_triage_learns_a_mode_that_the_next_run_uses(tmp_path: Path) -> None:
    seeds = [
        {"id": f"s{i}", "input": {"question": f"Which county is number {i}?"}} for i in range(22)
    ]
    originals = {s["input"]["question"] for s in seeds}
    cfg = make_config(tmp_path, seeds=seeds, relations=["typo-robustness"])

    def answer(payload: dict[str, Any], n: int) -> str:
        return "Nairobi" if payload["question"] in originals else "Kisumu"

    first = await run_suite(cfg, target=ScriptedTarget(answer))
    assert first.relations[0].mode is Mode.WARNING and first.relations[0].mode_source == "default"
    assert len(first.violations) == 22

    with open_store(cfg) as store:
        for case in first.violations[:20]:
            stats = store.triage(case.id, "true_bug")
        assert stats.reviewed == 20 and stats.precision == 1.0
        assert stats.learned_mode is Mode.BLOCKING

    second = await run_suite(cfg, target=ScriptedTarget(answer))
    assert (
        second.relations[0].mode is Mode.BLOCKING and second.relations[0].mode_source == "learned"
    )
    assert second.gate is not None and not second.gate.passed

    pinned = make_config(
        tmp_path, seeds=seeds, relations=[{"id": "typo-robustness", "mode": "warning"}]
    )
    third = await run_suite(pinned, target=ScriptedTarget(answer))
    assert third.relations[0].mode is Mode.WARNING and third.relations[0].mode_source == "config"
