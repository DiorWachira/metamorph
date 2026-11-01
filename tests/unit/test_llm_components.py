"""LLM transforms and the M2 comparators (embedding, entailment judge, verdict, refusal)."""

from __future__ import annotations

import json
import random

import pytest
from fakes import ScriptedLLM, rewrites

from metamorph.comparators import build_comparator
from metamorph.comparators.semantic import EmbeddingSimilarity
from metamorph.config import FieldsConfig
from metamorph.errors import ConfigError, NotComparable
from metamorph.llm.base import LLMError, LLMRequest
from metamorph.llm.service import LLMService
from metamorph.services import Services
from metamorph.transforms import Resources, TransformContext, build_transform

FIELDS = FieldsConfig(text="question")
SOURCE = {"question": "When did M-Pesa launch?"}


def ctx(variant: int = 0) -> TransformContext:
    return TransformContext(random.Random(0), FIELDS, Resources(), variant=variant)


def bound(name: str, params: dict[str, object], llm: ScriptedLLM):  # type: ignore[no-untyped-def]
    transform = build_transform(name, params)
    transform.bind(Services(llm=LLMService(llm)))
    return transform


async def test_paraphrase_rewrites_the_text_field() -> None:
    llm = ScriptedLLM(rewrites(lambda t: "In which year was M-Pesa launched?"))
    followup = await bound("paraphrase", {}, llm).aapply(SOURCE, ctx())
    assert followup is not None
    assert followup.input == {"question": "In which year was M-Pesa launched?"}
    assert followup.note.startswith("paraphrase: ")
    request = llm.requests[0]
    assert request.schema is not None and "When did M-Pesa launch?" in request.prompt


async def test_translate_roundtrip_chains_two_calls() -> None:
    steps = iter(["Lini M-Pesa ilizinduliwa?", "When was M-Pesa launched?"])
    llm = ScriptedLLM(rewrites(lambda t: next(steps)))
    t = bound("translate", {"language": "Kiswahili", "roundtrip": True}, llm)
    followup = await t.aapply(SOURCE, ctx())
    assert followup is not None and followup.input["question"] == "When was M-Pesa launched?"
    assert "Kiswahili" in llm.requests[0].prompt and "English" in llm.requests[1].prompt
    assert "Lini M-Pesa" in llm.requests[1].prompt


async def test_variants_ask_for_different_rewrites() -> None:
    llm = ScriptedLLM(rewrites(lambda t: "something else"))
    t = bound("code_switch", {"style": "sheng"}, llm)
    await t.aapply(SOURCE, ctx(0))
    await t.aapply(SOURCE, ctx(1))
    assert "alternative #2" in llm.requests[1].prompt
    assert "alternative" not in llm.requests[0].prompt


async def test_unchanged_rewrite_is_no_followup_and_empty_is_an_error() -> None:
    same = bound("formality", {}, ScriptedLLM(rewrites(lambda t: t + "  ")))
    assert await same.aapply(SOURCE, ctx()) is None
    empty = bound("negate", {}, ScriptedLLM(rewrites(lambda t: "")))
    with pytest.raises(LLMError, match="empty"):
        await empty.aapply(SOURCE, ctx())


def test_llm_components_need_an_llm_section() -> None:
    with pytest.raises(ConfigError, match="llm:"):
        build_transform("paraphrase", {}).bind(Services())
    with pytest.raises(ConfigError, match="llm:"):
        build_comparator("entails", {}).bind(Services())


def test_bad_llm_transform_params() -> None:
    with pytest.raises(ConfigError):
        build_transform("code_switch", {"style": "klingon"})
    with pytest.raises(ConfigError):
        build_transform("formality", {"direction": "rude"})


def judge_llm(verdict: str) -> ScriptedLLM:
    return ScriptedLLM(lambda r: json.dumps({"verdict": verdict, "reason": "because"}))


@pytest.mark.parametrize(
    ("verdict", "score"), [("ENTAILS", 1.0), ("NEUTRAL", 0.5), ("CONTRADICTS", 0.0)]
)
async def test_entails_scores(verdict: str, score: float) -> None:
    comparator = build_comparator("entails", {})
    comparator.bind(Services(llm=LLMService(judge_llm(verdict))))
    result = await comparator.acompare("2007", "It launched in 2007.")
    assert result.score == score and result.detail.startswith(verdict)


async def test_entails_short_circuits_identical_and_handles_failures() -> None:
    llm = judge_llm("CONTRADICTS")
    comparator = build_comparator("entails", {})
    comparator.bind(Services(llm=LLMService(llm)))
    assert (await comparator.acompare("same", " same ")).score == 1.0
    assert llm.requests == []

    broken = build_comparator("entails", {})
    broken.bind(Services(llm=LLMService(ScriptedLLM(lambda r: LLMError("down")))))
    with pytest.raises(NotComparable, match="judge unavailable"):
        await broken.acompare("a", "b")
    weird = build_comparator("entails", {})
    weird.bind(Services(llm=LLMService(judge_llm("MAYBE"))))
    with pytest.raises(NotComparable, match="unknown verdict"):
        await weird.acompare("a", "b")


async def test_embedding_similarity_with_injected_embedder() -> None:
    vectors = {"cat": [1.0, 0.0], "kitten": [0.9, 0.1], "car": [0.0, 1.0]}
    calls: list[list[str]] = []

    def embed(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        return [vectors[t] for t in texts]

    comparator = EmbeddingSimilarity(embedder=embed)
    assert (await comparator.acompare("cat", "kitten")).score > 0.95
    assert comparator.compare("cat", "car").score == 0.0
    assert comparator.compare("", "").score == 1.0
    assert sum(len(c) for c in calls) == 3  # each text embedded once


def test_verdict_labels() -> None:
    c = build_comparator("verdict", {})
    assert c.compare("Yes, it did.", "yes").score == 1.0
    assert c.compare("Yes.", "No, never.").score == 0.0
    with pytest.raises(NotComparable):
        c.compare("Perhaps", "No")
    by_path = build_comparator("verdict", {"labels": ["approve", "reject"], "path": "$.decision"})
    assert by_path.compare('{"decision": "approve"}', '{"decision": "reject"}').score == 0.0


def test_refusal_match() -> None:
    c = build_comparator("refusal_match", {})
    refusal = "I'm sorry, but I can't help with that."
    assert c.compare(refusal, "I cannot assist with this request.").score == 1.0
    assert c.compare(refusal, "Sure! Step one is...").score == 0.0
    assert c.compare("Samahani, siwezi kusaidia.", refusal).score == 1.0
    assert (
        c.compare("Here is the answer.", "The answer is 4.").detail
        == "source complied, follow-up complied"
    )


def test_request_fingerprint_is_stable() -> None:
    a = LLMRequest(system="s", prompt="p", schema={"b": 1, "a": 2})
    b = LLMRequest(system="s", prompt="p", schema={"a": 2, "b": 1})
    assert a.fingerprint() == b.fingerprint()
    assert a.fingerprint() != LLMRequest(system="s", prompt="q").fingerprint()
