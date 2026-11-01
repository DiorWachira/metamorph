"""The run pipeline: plan follow-ups, call the target once per unique input, judge every case.

1. Plan:  for each (seed, applicable relation, variant) apply the transform with an rng derived
          from (run seed, relation, seed, variant). Deterministic, so re-runs hit the cache.
2. Call:  collect unique (input, sample_idx) pairs (sources are shared across relations) and
          run them concurrently through the executor.
3. Judge: compare each follow-up with its k source samples against the self-variance baseline.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from metamorph.config import FieldsConfig, RunConfig
from metamorph.relations import Relation
from metamorph.runner.cache import cache_key
from metamorph.runner.executor import CallExecutor
from metamorph.runner.judge import judge
from metamorph.transforms import Resources, TransformContext
from metamorph.types import FollowUp, Input, Seed, TargetOutput, Verdict
from metamorph.util import derive_rng


@dataclass(frozen=True)
class PlannedCase:
    relation: Relation
    seed: Seed
    variant: int
    followup: FollowUp


@dataclass(frozen=True)
class Skip:
    relation_id: str
    seed_id: str
    reason: str


@dataclass(frozen=True)
class CaseResult:
    relation: Relation
    seed: Seed
    variant: int
    followup: FollowUp
    source_outputs: list[TargetOutput]
    followup_output: TargetOutput
    verdict: Verdict


def plan(
    relations: list[Relation],
    seeds: list[Seed],
    run: RunConfig,
    fields: FieldsConfig,
    resources: Resources,
) -> tuple[list[PlannedCase], list[Skip]]:
    planned: list[PlannedCase] = []
    skipped: list[Skip] = []
    for seed in seeds:
        for relation in relations:
            if not relation.applies_to(seed):
                continue  # tag mismatch is by design, not worth reporting
            if reason := relation.transform.missing(seed.input, fields):
                skipped.append(Skip(relation.id, seed.id, reason))
                continue
            for variant in range(relation.spec.followups):
                rng = derive_rng(run.seed, relation.id, seed.id, variant)
                ctx = TransformContext(rng=rng, fields=fields, resources=resources)
                followup = relation.transform.apply(seed.input, ctx)
                if followup is None:
                    skipped.append(Skip(relation.id, seed.id, "transform found nothing to change"))
                    break
                planned.append(PlannedCase(relation, seed, variant, followup))
    return planned, skipped


async def execute(
    planned: list[PlannedCase],
    executor: CallExecutor,
    run: RunConfig,
    on_total_calls: Callable[[int], None] | None = None,
) -> list[CaseResult]:
    calls: dict[str, tuple[Input, int]] = {}

    def need(payload: Input, sample_idx: int) -> str:
        key = cache_key("", payload, sample_idx)
        calls.setdefault(key, (payload, sample_idx))
        return key

    wiring = []
    for case in planned:
        source_keys = [need(case.seed.input, i) for i in range(run.samples)]
        followup_key = need(case.followup.input, 0)
        wiring.append((case, source_keys, followup_key))

    keys = list(calls)
    if on_total_calls:
        on_total_calls(len(keys))
    outputs = await asyncio.gather(*(executor.get(*calls[k]) for k in keys))
    by_key = dict(zip(keys, outputs, strict=True))

    results: list[CaseResult] = []
    for case, source_keys, followup_key in wiring:
        sources = [by_key[k] for k in source_keys]
        followup_output = by_key[followup_key]
        verdict = await judge(case.relation, sources, followup_output, case.followup, run.margin)
        results.append(
            CaseResult(
                case.relation,
                case.seed,
                case.variant,
                case.followup,
                sources,
                followup_output,
                verdict,
            )
        )
    return results
