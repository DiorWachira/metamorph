"""The report model: one run read back from storage. Every report format renders this."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from metamorph.types import Mode, Status


class OutputView(BaseModel):
    sample_idx: int
    text: str
    latency_ms: float
    cost_usd: float
    cached: bool
    error: str | None = None


class CaseView(BaseModel):
    id: int
    relation_id: str
    seed_id: str
    variant: int
    mode: Mode
    status: Status
    score: float | None
    threshold: float
    self_variance: float | None
    detail: str
    followup_note: str
    source_input: dict[str, Any]
    followup_input: dict[str, Any]
    source_outputs: list[OutputView]
    followup_output: OutputView
    triage: str


class RelationSummary(BaseModel):
    id: str
    mode: Mode
    cases: int = 0
    passed: int = 0
    violations: int = 0
    inconclusive: int = 0
    errors: int = 0


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


class RunView(BaseModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    git_sha: str | None
    status: str
    total_cost_usd: float
    stats: dict[str, Any]


class RunReport(BaseModel):
    run: RunView
    gate: GateResult | None
    relations: list[RelationSummary]
    cases: list[CaseView]
    skipped: list[SkipView]

    @property
    def violations(self) -> list[CaseView]:
        return [c for c in self.cases if c.status is Status.VIOLATION]
