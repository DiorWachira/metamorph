from __future__ import annotations

import random

import pytest

from metamorph.config import FieldsConfig
from metamorph.errors import ConfigError
from metamorph.transforms import Resources, TransformContext, build_transform
from metamorph.transforms.numbers import canonical_numbers, group_thousands, ungroup_thousands
from metamorph.transforms.text import add_typos

DOCS = ["Alpha doc about rain.", "Beta doc about sun.", "Gamma doc about wind."]


def test_unknown_transform_and_bad_params_are_config_errors() -> None:
    with pytest.raises(ConfigError, match="unknown transform"):
        build_transform("nope", {})
    with pytest.raises(ConfigError, match="bad params"):
        build_transform("typos", {"rate": 3})
    with pytest.raises(ConfigError, match="bad params"):
        build_transform("typos", {"speed": 1})


class TestShuffleDocuments:
    def test_reorders_without_losing_documents(self, ctx: TransformContext) -> None:
        source = {"question": "q", "documents": DOCS}
        followup = build_transform("shuffle_documents", {}).apply(source, ctx)
        assert followup is not None
        assert followup.input["documents"] != DOCS
        assert sorted(followup.input["documents"]) == sorted(DOCS)
        assert source["documents"] == DOCS  # the source is never mutated

    def test_nothing_to_shuffle(self, ctx: TransformContext) -> None:
        t = build_transform("shuffle_documents", {})
        assert t.apply({"documents": ["only"]}, ctx) is None
        assert t.apply({"documents": ["same", "same"]}, ctx) is None

    def test_missing_field_reason(self, fields: FieldsConfig) -> None:
        t = build_transform("shuffle_documents", {})
        assert "documents" in (t.missing({"question": "q"}, fields) or "")
        assert t.missing({"question": "q"}, FieldsConfig(text="question")) is not None

    def test_nested_paths(self, resources: Resources) -> None:
        fields = FieldsConfig(documents="ctx.chunks")
        ctx = TransformContext(random.Random(1), fields, resources)
        followup = build_transform("shuffle_documents", {}).apply({"ctx": {"chunks": DOCS}}, ctx)
        assert followup is not None
        assert sorted(followup.input["ctx"]["chunks"]) == sorted(DOCS)


class TestInjectDistractor:
    def test_inserts_into_documents(self, ctx: TransformContext) -> None:
        source = {"question": "q", "documents": DOCS}
        followup = build_transform("inject_distractor", {"position": "start"}).apply(source, ctx)
        assert followup is not None
        docs = followup.input["documents"]
        assert len(docs) == 4 and docs[1:] == DOCS
        assert docs[0] in ctx.resources.distractors

    def test_matches_object_documents(self, ctx: TransformContext) -> None:
        source = {"documents": [{"text": "a", "id": 1}, {"text": "b", "id": 2}]}
        followup = build_transform("inject_distractor", {"position": "end"}).apply(source, ctx)
        assert followup is not None
        added = followup.input["documents"][-1]
        assert set(added) == {"text", "id"} and added["text"] in ctx.resources.distractors

    def test_falls_back_to_text(self, ctx: TransformContext) -> None:
        source = {"question": "What is the capital?"}
        followup = build_transform("inject_distractor", {"position": "end"}).apply(source, ctx)
        assert followup is not None
        assert followup.input["question"].startswith("What is the capital?\n\n")

    def test_rejects_bad_position(self) -> None:
        with pytest.raises(ConfigError):
            build_transform("inject_distractor", {"position": "middle"})


class TestTypos:
    def test_changes_text_but_keeps_short_words_and_numbers(self) -> None:
        text = "Is the bank open on 25 December in Nairobi city?"
        noisy = add_typos(text, rate=1.0, rng=random.Random(3))
        assert noisy != text
        for keep in ("Is", "the", "25", "on", "in"):
            assert keep in noisy.split()

    def test_rate_zero_is_identity(self) -> None:
        assert add_typos("Hello wonderful world", 0.0, random.Random(1)) == "Hello wonderful world"

    def test_returns_none_when_nothing_eligible(self, ctx: TransformContext) -> None:
        assert build_transform("typos", {}).apply({"question": "is it ok?"}, ctx) is None


class TestNumberFormat:
    def test_group_and_ungroup(self) -> None:
        assert group_thousands("pay 1000 or 25000000 now") == "pay 1,000 or 25,000,000 now"
        assert ungroup_thousands("pay 1,000 or 25,000,000") == "pay 1000 or 25000000"

    def test_leaves_years_ids_phones_and_decimals_alone(self) -> None:
        text = "In 2019 call 0712345678 about KE1234, pi is 3.14159"
        assert group_thousands(text) == text
        assert group_thousands("1234.5 units") == "1,234.5 units"
        assert group_thousands("in 2019", skip_years=False) == "in 2,019"

    def test_auto_direction_and_output_normaliser(self, ctx: TransformContext) -> None:
        t = build_transform("number_format", {})
        plain = t.apply({"question": "Is 5000 shillings enough?"}, ctx)
        assert plain is not None and plain.input["question"] == "Is 5,000 shillings enough?"
        grouped = t.apply({"question": "Is 5,000 shillings enough?"}, ctx)
        assert grouped is not None and grouped.input["question"] == "Is 5000 shillings enough?"
        assert plain.normalize is not None
        assert plain.normalize("about 12,500 KES") == "about 12500 KES"
        assert canonical_numbers("1,000,000") == "1000000"

    def test_scope_all_rewrites_documents(self, ctx: TransformContext) -> None:
        source = {"question": "How tall?", "documents": ["It rises 5199 metres."]}
        assert build_transform("number_format", {}).apply(source, ctx) is None
        followup = build_transform("number_format", {"scope": "all"}).apply(source, ctx)
        assert followup is not None and followup.input["documents"] == ["It rises 5,199 metres."]


class TestSwapEntities:
    def test_swaps_consistently_and_maps_back(self, ctx: TransformContext) -> None:
        source = {"question": "Did Wanjiru pay Kamau?", "documents": ["Wanjiru owes Kamau 50."]}
        followup = build_transform("swap_entities", {}).apply(source, ctx)
        assert followup is not None
        question = followup.input["question"]
        assert "Wanjiru" not in question and "Kamau" not in question
        new_wanjiru = question.split()[1]
        assert followup.input["documents"][0].startswith(new_wanjiru)
        assert followup.normalize is not None
        assert followup.normalize(f"Yes, {new_wanjiru} paid.") == "Yes, Wanjiru paid."

    def test_whole_words_only(self, ctx: TransformContext) -> None:
        assert build_transform("swap_entities", {}).apply({"question": "Marysville"}, ctx) is None

    def test_place_category(self, ctx: TransformContext) -> None:
        t = build_transform("swap_entities", {"categories": ["place"]})
        followup = t.apply({"question": "Is Kisumu far?"}, ctx)
        assert followup is not None and "Kisumu" not in followup.input["question"]


class TestSurfaceNoise:
    def test_changes_surface_only(self, ctx: TransformContext) -> None:
        source = {"question": "Extract the skills from this CV."}
        followup = build_transform("surface_noise", {}).apply(source, ctx)
        assert followup is not None
        noisy = followup.input["question"]
        assert noisy != source["question"]
        assert noisy.split()[1:4] == ["the", "skills", "from"]
