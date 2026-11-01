"""Learned relation modes: a relation blocks CI only after triage shows it is usually right.

precision = true_bugs / (true_bugs + false_alarms) over every triaged violation of the relation.
With at least MIN_REVIEWED triaged violations, precision >= MIN_PRECISION promotes it to
BLOCKING and anything lower demotes it to WARNING. Below MIN_REVIEWED nothing is learned yet.
A `mode:` pinned in metamorph.yaml always wins over the learned mode.
"""

from __future__ import annotations

from metamorph.types import Mode

MIN_REVIEWED = 20
MIN_PRECISION = 0.8


def precision(true_bugs: int, false_alarms: int) -> float | None:
    reviewed = true_bugs + false_alarms
    return true_bugs / reviewed if reviewed else None


def learned_mode(true_bugs: int, false_alarms: int) -> Mode | None:
    if true_bugs + false_alarms < MIN_REVIEWED:
        return None
    p = precision(true_bugs, false_alarms)
    return Mode.BLOCKING if p is not None and p >= MIN_PRECISION else Mode.WARNING
