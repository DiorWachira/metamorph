"""CI gate: decide pass/fail from blocking violations and the target error rate."""

from __future__ import annotations

from metamorph.config import GateConfig
from metamorph.reports.model import GateResult
from metamorph.runner.engine import CaseResult
from metamorph.types import Mode, Status


def evaluate_gate(results: list[CaseResult], gate: GateConfig) -> GateResult:
    blocking = [r for r in results if r.relation.mode is Mode.BLOCKING]
    violations = sum(r.verdict.status is Status.VIOLATION for r in blocking)
    errors = sum(r.verdict.status is Status.ERROR for r in results)
    error_rate = errors / len(results) if results else 0.0

    reasons: list[str] = []
    if violations > gate.max_blocking_violations:
        reasons.append(f"{violations} blocking violations > allowed {gate.max_blocking_violations}")
    if gate.max_blocking_rate is not None and blocking:
        rate = violations / len(blocking)
        if rate > gate.max_blocking_rate:
            reasons.append(f"blocking violation rate {rate:.1%} > {gate.max_blocking_rate:.1%}")
    too_many_errors = error_rate > gate.max_error_rate
    if too_many_errors:
        reasons.append(f"target error rate {error_rate:.1%} > {gate.max_error_rate:.1%}")

    return GateResult(
        passed=not reasons,
        blocking_violations=violations,
        blocking_cases=len(blocking),
        error_rate=error_rate,
        too_many_errors=too_many_errors,
        reasons=reasons,
    )
