"""The relation miner, proposal decisions, custom relations and learned modes on file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fakes import ScriptedLLM, ScriptedTarget
from support import make_config

from metamorph.collection import (
    decide,
    load_custom,
    load_learned,
    load_proposals,
    proposals_path,
    save_learned,
    save_proposals,
)
from metamorph.errors import ConfigError, MetamorphError
from metamorph.llm.service import LLMService
from metamorph.miner import mine, mine_request, vocabulary
from metamorph.relations import builtin_specs, resolve_relations
from metamorph.storage.repo import RelationStats
from metamorph.suite import run_suite
from metamorph.transforms.base import registry
from metamorph.types import Mode

SPEC = "1. The order of sentences must not change the answer.\n2. Names must not matter."


def raw(rel_id: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "id": rel_id,
        "requirement": "The order of sentences must not change the answer.",
        "description": "Reordering sentences keeps the answer.",
        "transform": "rewrite",
        "transform_params_json": json.dumps({"instruction": "Reverse the sentence order."}),
        "comparator": "token_f1",
        "comparator_params_json": "{}",
        "threshold": 0.8,
        "expected": "invariant",
        "rationale": "Catches order dependence.",
    }
    return base | overrides


def miner_llm(*proposals: dict[str, Any]) -> LLMService:
    return LLMService(ScriptedLLM(lambda r: json.dumps({"proposals": list(proposals)})))


def test_vocabulary_lists_every_component_with_its_own_docs() -> None:
    text = vocabulary()
    assert all(f"- {name}" in text for name in registry())
    assert "Helper class" not in text  # docstrings are never inherited from ABC
    assert "rewrite(instruction)" in text and "shuffle_documents:" in text
    request = mine_request(SPEC, "a CV app")
    assert "a CV app" in request.prompt and SPEC in request.prompt
    enum = request.schema["properties"]["proposals"]["items"]["properties"]["transform"]["enum"]  # type: ignore[index]
    assert set(enum) == set(registry())


async def test_mine_keeps_valid_proposals_and_explains_the_rest() -> None:
    llm = miner_llm(
        raw("sentence-order-invariance"),
        raw("Bad Id"),
        raw("typo-robustness"),  # clashes with a built-in
        raw("broken-params", comparator_params_json="{nope"),
        raw("wrong-param", comparator="numeric_within", comparator_params_json='{"tolerance": 1}'),
        raw("empty-rewrite", transform_params_json='{"instruction": ""}'),
        raw("sentence-order-invariance"),  # duplicate within the batch
    )
    result = await mine(llm, SPEC, "SPEC.md", set(builtin_specs()))
    assert [p.spec.id for p in result.proposals] == ["sentence-order-invariance"]
    proposal = result.proposals[0]
    assert proposal.spec.requirement and proposal.source == "SPEC.md"
    assert proposal.model == "scripted-llm"
    reasons = dict(result.rejected)
    assert "kebab-case" in reasons["Bad Id"]
    assert "clashes" in reasons["typo-robustness"]
    assert "not JSON" in reasons["broken-params"]
    assert "tolerance" in reasons["wrong-param"]
    assert "instruction" in reasons["empty-rewrite"]


async def test_mine_rejects_empty_specs() -> None:
    with pytest.raises(ConfigError, match="empty"):
        await mine(miner_llm(), "  ", "x", set())


async def test_approve_reject_and_auto_enable(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    result = await mine(
        miner_llm(raw("sentence-order-invariance"), raw("names-do-not-matter")),
        SPEC,
        "SPEC.md",
        set(builtin_specs()),
    )
    save_proposals(proposals_path(cfg), result.proposals)

    decide(cfg, ["sentence-order-invariance"], "approved")
    decide(cfg, ["names-do-not-matter"], "rejected")
    with pytest.raises(MetamorphError, match="no pending proposal"):
        decide(cfg, ["names-do-not-matter"], "approved")

    statuses = {p.spec.id: p.status for p in load_proposals(proposals_path(cfg))}
    assert statuses == {"sentence-order-invariance": "approved", "names-do-not-matter": "rejected"}
    custom = load_custom(cfg.resolve(cfg.custom_relations))
    assert [s.id for s in custom] == ["sentence-order-invariance"]

    ids = [r.id for r in resolve_relations(cfg)]
    assert ids == ["typo-robustness", "sentence-order-invariance"]  # enabled without listing it


def test_custom_relations_file_errors(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    path = cfg.resolve(cfg.custom_relations)
    path.parent.mkdir(parents=True)
    path.write_text("not: a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="list"):
        resolve_relations(cfg)
    path.write_text("- id: half\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid relation"):
        resolve_relations(cfg)


def test_learned_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "relations" / "learned.yaml"
    stats = [
        RelationStats(
            relation_id="a",
            reviewed=20,
            true_bugs=19,
            false_alarms=1,
            precision=0.95,
            learned_mode=Mode.BLOCKING,
        ),
        RelationStats(
            relation_id="b",
            reviewed=3,
            true_bugs=1,
            false_alarms=2,
            precision=1 / 3,
            learned_mode=None,
        ),
    ]
    save_learned(path, stats)
    assert load_learned(path) == {"a": Mode.BLOCKING}
    assert "precision: 0.333" in path.read_text(encoding="utf-8")
    path.write_text("a: {mode: sometimes}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown mode"):
        load_learned(path)


async def test_ci_applies_modes_from_the_committed_file(tmp_path: Path) -> None:
    """In CI the database is empty; relations/learned.yaml still carries the earned trust."""
    cfg = make_config(tmp_path, relations=["typo-robustness"])  # mode not pinned in config
    learned = cfg.resolve(cfg.learned_modes)
    learned.parent.mkdir(parents=True)
    learned.write_text("typo-robustness: {mode: blocking}\n", encoding="utf-8")
    report = await run_suite(cfg, target=ScriptedTarget(lambda p, n: "same"))
    (relation,) = report.relations
    assert relation.mode is Mode.BLOCKING and relation.mode_source == "learned"


def test_committed_replay_recordings_are_current() -> None:
    """The CV demo's recordings must match the requests Metamorph sends today."""
    import importlib.util
    import sys

    example = Path(__file__).parents[2] / "examples" / "cv_skills"
    committed = (example / "recordings.jsonl").read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "author_recordings", example / "author_recordings.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(example))
    try:
        spec.loader.exec_module(module)
        written: dict[str, str] = {}
        original = Path.write_text

        def capture(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
            written[self.name] = data
            return len(data)

        Path.write_text = capture  # type: ignore[method-assign]
        try:
            module.main()
        finally:
            Path.write_text = original  # type: ignore[method-assign]
    finally:
        sys.path.remove(str(example))
    assert written["recordings.jsonl"] == committed, (
        "recordings.jsonl is stale: run `python author_recordings.py` in examples/cv_skills"
    )
