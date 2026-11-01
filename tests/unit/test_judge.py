from __future__ import annotations

from metamorph.config import ComparatorSpec, RelationSpec, TransformSpec
from metamorph.relations import Relation
from metamorph.runner.judge import judge
from metamorph.types import Expectation, FollowUp, Status, TargetOutput


def relation(expected: Expectation = Expectation.INVARIANT, threshold: float = 0.8) -> Relation:
    return Relation.from_spec(
        RelationSpec(
            id="r",
            description="test",
            transform=TransformSpec(name="typos"),
            comparator=ComparatorSpec(name="token_f1", threshold=threshold),
            expected=expected,
        )
    )


def out(text: str) -> TargetOutput:
    return TargetOutput(text=text, latency_ms=1.0)


FOLLOWUP = FollowUp(input={}, note="n")


async def test_invariant_pass_and_violation() -> None:
    passed = await judge(relation(), [out("a b c d")], out("a b c d"), FOLLOWUP, 0.05)
    assert passed.status is Status.PASS and passed.self_variance is None
    failed = await judge(relation(), [out("a b c d")], out("w x y z"), FOLLOWUP, 0.05)
    assert failed.status is Status.VIOLATION and failed.threshold == 0.8


async def test_self_variance_excuses_noise_the_target_makes_on_its_own() -> None:
    # The source samples only agree with each other at F1 0.5, so a follow-up at 0.5 is noise.
    sources = [out("a b c d"), out("a b x y")]
    verdict = await judge(relation(), sources, out("a b p q"), FOLLOWUP, margin=0.05)
    assert verdict.self_variance == 0.5
    assert verdict.threshold == 0.45
    assert verdict.status is Status.PASS


async def test_self_variance_still_flags_bigger_disagreement() -> None:
    sources = [out("a b c d"), out("a b x y")]
    verdict = await judge(relation(), sources, out("p q r s"), FOLLOWUP, margin=0.05)
    assert verdict.status is Status.VIOLATION


async def test_stable_source_keeps_the_threshold() -> None:
    sources = [out("a b c d")] * 3
    verdict = await judge(relation(), sources, out("a b c x"), FOLLOWUP, margin=0.05)
    assert verdict.self_variance == 1.0 and verdict.threshold == 0.8
    assert verdict.status is Status.VIOLATION  # F1 0.75 < 0.8


async def test_flips() -> None:
    rel = relation(Expectation.FLIPS, threshold=1.0)
    assert (await judge(rel, [out("yes")], out("no"), FOLLOWUP, 0.0)).status is Status.PASS
    same = await judge(rel, [out("yes")], out("Yes"), FOLLOWUP, 0.0)
    assert same.status is Status.VIOLATION


async def test_normaliser_applies_before_comparison() -> None:
    followup = FollowUp(input={}, note="n", normalize=lambda t: t.replace("Achieng", "Wanjiru"))
    verdict = await judge(relation(), [out("Wanjiru paid")], out("Achieng paid"), followup, 0.0)
    assert verdict.status is Status.PASS


async def test_errors_and_inconclusive() -> None:
    failed = TargetOutput(text="", latency_ms=1.0, error="boom")
    assert (await judge(relation(), [failed], out("x"), FOLLOWUP, 0)).status is Status.ERROR
    assert (await judge(relation(), [out("x")], failed, FOLLOWUP, 0)).status is Status.ERROR

    schema = Relation.from_spec(
        RelationSpec(
            id="s",
            description="d",
            transform=TransformSpec(name="surface_noise"),
            comparator=ComparatorSpec(name="json_schema_equal"),
        )
    )
    verdict = await judge(schema, [out("not json")], out("{}"), FOLLOWUP, 0)
    assert verdict.status is Status.INCONCLUSIVE
