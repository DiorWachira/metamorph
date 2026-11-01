"""Turn outputs into a verdict, discounting the target's own non-determinism.

With k source samples, the self-variance baseline is the lowest agreement between any two of
them. An invariance relation is violated only when the follow-up agrees with the source less
than the source agrees with itself (minus a margin), and less than the comparator threshold:

    violation  <=>  best_score < min(threshold, baseline - margin)

so a stable target is held to the threshold, and an unstable one is not blamed for noise it
produces on its own. With k = 1 there is no baseline and the threshold applies.
"""

from __future__ import annotations

from itertools import combinations

from metamorph.errors import NotComparable
from metamorph.relations import Relation
from metamorph.types import Comparison, Expectation, FollowUp, Status, TargetOutput, Verdict


async def judge(
    relation: Relation,
    sources: list[TargetOutput],
    followup_output: TargetOutput,
    followup: FollowUp,
    margin: float,
) -> Verdict:
    threshold = relation.threshold
    ok_sources = [s for s in sources if s.ok]
    if not ok_sources:
        return Verdict(Status.ERROR, None, threshold, None, f"source failed: {sources[0].error}")
    if not followup_output.ok:
        return Verdict(
            Status.ERROR, None, threshold, None, f"follow-up failed: {followup_output.error}"
        )

    normalize = followup.normalize or (lambda text: text)
    source_texts = [normalize(s.text) for s in ok_sources]
    followup_text = normalize(followup_output.text)
    comparator = relation.comparator

    try:
        comparisons = [await comparator.acompare(a, followup_text) for a in source_texts]
        pairwise = [await comparator.acompare(a, b) for a, b in combinations(source_texts, 2)]
    except NotComparable as exc:
        return Verdict(Status.INCONCLUSIVE, None, threshold, None, str(exc))

    baseline = min((c.score for c in pairwise), default=None)
    best: Comparison = max(comparisons, key=lambda c: c.score)

    if relation.expected is Expectation.INVARIANT:
        effective = threshold if baseline is None else min(threshold, baseline - margin)
        violated = best.score < effective
    else:
        # A flip must disagree with every source sample; noise cannot excuse agreement.
        effective = threshold
        violated = best.score >= threshold

    detail = best.detail
    if baseline is not None:
        detail += f" (self-agreement {baseline:.2f}, threshold {effective:.2f})"
    return Verdict(
        status=Status.VIOLATION if violated else Status.PASS,
        score=best.score,
        threshold=effective,
        self_variance=baseline,
        detail=detail,
        comparisons=comparisons,
    )
