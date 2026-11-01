from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedTarget
from test_suite import SEEDS, make_config

from metamorph.errors import MetamorphError
from metamorph.promotion import MIN_REVIEWED, learned_mode, precision
from metamorph.suite import open_store, run_suite
from metamorph.types import Mode


def test_promotion_policy() -> None:
    assert precision(0, 0) is None
    assert precision(8, 2) == 0.8
    assert learned_mode(15, 0) is None  # not enough evidence yet
    assert learned_mode(16, 4) is Mode.BLOCKING  # 0.8 at exactly MIN_REVIEWED
    assert learned_mode(15, 5) is Mode.WARNING  # demoted
    assert MIN_REVIEWED == 20


async def test_triage_rules_and_stats(tmp_path: Path) -> None:
    originals = {s["input"]["question"] for s in SEEDS}
    cfg = make_config(tmp_path)
    report = await run_suite(
        cfg, target=ScriptedTarget(lambda p, n: "A" if p["question"] in originals else "B")
    )
    violation, *_ = report.violations
    with open_store(cfg) as store:
        stats = store.triage(violation.id, "false_alarm", note="typo hit a name")
        assert (stats.reviewed, stats.false_alarms, stats.precision) == (1, 1, 0.0)
        case = store.load_case(violation.id)
        assert case is not None and case.triage == "false_alarm" and case.note == "typo hit a name"

        stats = store.triage(violation.id, "unreviewed")  # undo
        assert stats.reviewed == 0 and stats.precision is None
        assert store.relation_stats()[0].relation_id == "typo-robustness"

        with pytest.raises(MetamorphError, match="no case"):
            store.triage(99999, "true_bug")

        runs = store.list_runs()
        assert runs[0].id == report.run.id and runs[0].violations == len(report.violations)


async def test_only_violations_can_be_triaged(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    report = await run_suite(cfg, target=ScriptedTarget(lambda p, n: "same"))
    with open_store(cfg) as store, pytest.raises(MetamorphError, match="only violations"):
        store.triage(report.cases[0].id, "true_bug")
