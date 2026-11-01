"""The report model: one run read back from storage. Every report format and the UI render this."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, computed_field

from metamorph.types import Mode, Status

Triage = Literal["unreviewed", "true_bug", "false_alarm"]


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


class OutputView(BaseModel):
    sample_idx: int
    text: str
    latency_ms: float
    cost_usd: float
    cached: bool
    error: str | None = None


class CaseView(BaseModel):
    id: int
    run_id: str
    relation_id: str
    seed_id: str
    variant: int
    mode: Mode
    status: Status
    score: float | None
    threshold: float  # applied threshold (after the self-variance baseline)
    nominal_threshold: float | None  # the comparator's own threshold
    self_variance: float | None
    detail: str
    followup_note: str
    source_input: dict[str, Any]
    followup_input: dict[str, Any]
    source_outputs: list[OutputView]
    followup_output: OutputView
    triage: Triage
    note: str | None = None

    def changed_field(self) -> tuple[str | None, str, str]:
        """The first input field the transform changed, as (name, before, after) text."""
        for key, after in self.followup_input.items():
            before = self.source_input.get(key)
            if before != after:
                if isinstance(before, str) and isinstance(after, str):
                    return key, before, after
                return key, _pretty(before), _pretty(after)
        return None, "", ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def excused_by_baseline(self) -> bool:
        """Below the comparator threshold, but within the target's own noise: not a violation."""
        return (
            self.status is Status.PASS
            and self.score is not None
            and self.nominal_threshold is not None
            and self.score < self.nominal_threshold
        )


class RelationSummary(BaseModel):
    id: str
    mode: Mode
    mode_source: str = "default"
    description: str = ""
    transform: str = ""
    comparator: str = ""
    threshold: float | None = None
    expected: str = "invariant"
    cases: int = 0
    passed: int = 0
    violations: int = 0
    inconclusive: int = 0
    errors: int = 0
    skipped: int = 0
    excused: int = 0  # would have been violations without the self-variance baseline


class GateResult(BaseModel):
    passed: bool  # blocking violations within limits
    blocking_violations: int
    blocking_cases: int
    error_rate: float
    too_many_errors: bool  # the target itself is failing: a runtime error, not a verdict
    reasons: list[str]


class SkipView(BaseModel):
    relation_id: str
    seed_id: str
    reason: str


class UnstableInput(BaseModel):
    """A seed the target answers inconsistently on its own, before any transform."""

    seed_id: str
    comparator: str
    self_agreement: float
    threshold: float
    relations: list[str]  # the relations whose verdicts this noise affected


class RunView(BaseModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    git_sha: str | None
    status: str
    total_cost_usd: float
    stats: dict[str, Any]
    llm: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    samples: int = 1


class RunReport(BaseModel):
    run: RunView
    gate: GateResult | None
    relations: list[RelationSummary]
    cases: list[CaseView]
    skipped: list[SkipView]

    @property
    def violations(self) -> list[CaseView]:
        return [c for c in self.cases if c.status is Status.VIOLATION]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unstable_inputs(self) -> list[UnstableInput]:
        """Seeds whose own samples agree below the comparator threshold, lowest first.

        One entry per (seed, comparator): relations sharing a comparator share the measurement.
        """
        comparators = {r.id: r.comparator for r in self.relations}
        found: dict[tuple[str, str], UnstableInput] = {}
        for c in self.cases:
            if c.self_variance is None or c.nominal_threshold is None:
                continue
            if c.self_variance >= c.nominal_threshold:
                continue
            comparator = comparators.get(c.relation_id, "")
            entry = found.setdefault(
                (c.seed_id, comparator),
                UnstableInput(
                    seed_id=c.seed_id,
                    comparator=comparator,
                    self_agreement=c.self_variance,
                    threshold=c.nominal_threshold,
                    relations=[],
                ),
            )
            entry.self_agreement = min(entry.self_agreement, c.self_variance)
            if c.relation_id not in entry.relations:
                entry.relations.append(c.relation_id)
        return sorted(found.values(), key=lambda u: u.self_agreement)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def baseline_effect(self) -> dict[str, int]:
        """Violations with and without the self-variance baseline: the false alarms it removed."""
        actual = len(self.violations)
        excused = sum(c.excused_by_baseline for c in self.cases)
        return {"naive_violations": actual + excused, "violations": actual, "excused": excused}
