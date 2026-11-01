"""Core value types passed between the planner, runner, judge and storage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

Input = dict[str, Any]


class Mode(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


class Expectation(StrEnum):
    INVARIANT = "invariant"  # follow-up output must agree with the source output
    FLIPS = "flips"  # follow-up output must disagree (e.g. negating a yes/no question)


class Status(StrEnum):
    PASS = "pass"
    VIOLATION = "violation"
    INCONCLUSIVE = "inconclusive"  # the comparator could not judge the pair
    ERROR = "error"  # the target failed on the source or follow-up
    SKIPPED = "skipped"  # not run: the cost budget ran out first


@dataclass(frozen=True)
class Seed:
    id: str
    input: Input
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FollowUp:
    """A transformed input plus what changed.

    `normalize` is applied to BOTH outputs before comparison. Transforms use it to undo
    their own surface effect, e.g. mapping swapped entity names back to the originals.
    """

    input: Input
    note: str
    normalize: Callable[[str], str] | None = None


@dataclass(frozen=True)
class TargetOutput:
    text: str
    latency_ms: float
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float = 0.0
    cached: bool = False
    error: str | None = None
    skipped: bool = False  # never called because the budget was exhausted

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class Comparison:
    """How much two outputs agree, from 0.0 (not at all) to 1.0 (fully)."""

    score: float
    detail: str = ""


@dataclass(frozen=True)
class Verdict:
    status: Status
    score: float | None  # best agreement between the follow-up and any source sample
    threshold: float  # the agreement threshold actually applied (after the baseline)
    self_variance: float | None  # min pairwise agreement among source samples (None if k=1)
    detail: str = ""
    comparisons: list[Comparison] = field(default_factory=list)
    nominal_threshold: float | None = None  # the comparator threshold before the baseline

    @property
    def excused_by_baseline(self) -> bool:
        """Would have been a violation without the self-variance baseline."""
        return (
            self.status is Status.PASS
            and self.score is not None
            and self.nominal_threshold is not None
            and self.score < self.nominal_threshold
        )

    @property
    def is_violation(self) -> bool:
        return self.status is Status.VIOLATION
