"""Hypothesis properties of the deterministic transforms."""

from __future__ import annotations

import random
import re

from hypothesis import given
from hypothesis import strategies as st

from metamorph.config import FieldsConfig
from metamorph.transforms import Resources, TransformContext, build_transform
from metamorph.transforms.numbers import canonical_numbers, group_thousands, ungroup_thousands
from metamorph.transforms.text import add_typos

RESOURCES = Resources.load()
FIELDS = FieldsConfig(text="question", documents="documents")
seeds = st.integers(min_value=0, max_value=2**32)
words = st.text(alphabet=st.characters(categories=["L"]), min_size=1, max_size=12)
sentences = st.lists(words, min_size=1, max_size=20).map(" ".join)


def ctx(seed: int) -> TransformContext:
    return TransformContext(random.Random(seed), FIELDS, RESOURCES)


@given(st.lists(st.text(max_size=30), min_size=2, max_size=8, unique=True), seeds)
def test_shuffle_is_a_real_permutation(docs: list[str], seed: int) -> None:
    followup = build_transform("shuffle_documents", {}).apply({"documents": docs}, ctx(seed))
    assert followup is not None
    out = followup.input["documents"]
    assert sorted(out) == sorted(docs) and out != docs


@given(st.lists(st.text(max_size=30), min_size=0, max_size=6), seeds)
def test_distractor_keeps_original_documents_in_order(docs: list[str], seed: int) -> None:
    followup = build_transform("inject_distractor", {}).apply({"documents": docs}, ctx(seed))
    assert followup is not None
    out = list(followup.input["documents"])
    assert len(out) == len(docs) + 1
    inserted = next(i for i in range(len(out)) if out[:i] + out[i + 1 :] == docs)
    assert out[inserted] in RESOURCES.distractors


@given(sentences, seeds)
def test_typos_rate_zero_is_identity(text: str, seed: int) -> None:
    assert add_typos(text, 0.0, random.Random(seed)) == text


@given(sentences, st.floats(min_value=0.01, max_value=1.0), seeds)
def test_typos_preserve_word_count(text: str, rate: float, seed: int) -> None:
    assert len(add_typos(text, rate, random.Random(seed)).split()) == len(text.split())


@given(sentences, st.floats(min_value=0.01, max_value=1.0), seeds)
def test_typos_are_deterministic_under_a_seed(text: str, rate: float, seed: int) -> None:
    assert add_typos(text, rate, random.Random(seed)) == add_typos(text, rate, random.Random(seed))


numbers = st.integers(min_value=1, max_value=10**12)
prose = st.lists(st.one_of(numbers.map(str), st.sampled_from(["cost", "is", "KES", "and"])))


@given(prose.map(" ".join))
def test_number_format_round_trips_values(text: str) -> None:
    def values(s: str) -> list[int]:
        return [int(n) for n in re.findall(r"\d+", canonical_numbers(s))]

    grouped = group_thousands(text, skip_years=False)
    assert values(grouped) == values(text)
    assert ungroup_thousands(grouped) == text


@given(sentences, seeds)
def test_entity_swap_normaliser_inverts_the_swap(text: str, seed: int) -> None:
    source = {"question": f"Wanjiru and Otieno said {text}"}
    followup = build_transform("swap_entities", {}).apply(source, ctx(seed))
    assert followup is not None and followup.normalize is not None
    assert followup.normalize(followup.input["question"]) == source["question"]
