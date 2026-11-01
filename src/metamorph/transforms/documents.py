"""Transforms over retrieved context: reorder it, or add an irrelevant paragraph."""

from __future__ import annotations

import copy
from typing import Any, Literal

from metamorph.config import FieldsConfig
from metamorph.transforms.base import (
    Transform,
    TransformContext,
    documents_of,
    register,
    text_of,
)
from metamorph.types import FollowUp, Input
from metamorph.util import has_path, with_path


@register
class ShuffleDocuments(Transform):
    """Permute the retrieved documents. A correct RAG answer should not depend on their order."""

    name = "shuffle_documents"
    requires = ("documents",)

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        assert ctx.fields.documents is not None
        docs = documents_of(source, ctx.fields)
        if len({repr(d) for d in docs}) < 2:
            return None
        order = list(range(len(docs)))
        for _ in range(10):
            ctx.rng.shuffle(order)
            if order != sorted(order):
                break
        else:  # vanishingly unlikely for n >= 2, but guarantee a real change
            order = order[1:] + order[:1]
        shuffled = [docs[i] for i in order]
        return FollowUp(
            input=with_path(source, ctx.fields.documents, shuffled),
            note=f"documents reordered to {order}",
        )


@register
class InjectDistractor(Transform):
    """Add an irrelevant paragraph from the distractor bank.

    It goes into the documents list when one is configured, otherwise it is appended or
    prepended to the main text field.
    """

    name = "inject_distractor"

    def __init__(self, position: Literal["random", "start", "end"] = "random") -> None:
        if position not in ("random", "start", "end"):
            raise ValueError(f"position must be random, start or end, not {position!r}")
        self.position = position

    def missing(self, source: Input, fields: FieldsConfig) -> str | None:
        if fields.documents is not None and has_path(source, fields.documents):
            return None
        if fields.text is not None and has_path(source, fields.text):
            return None
        return "input has neither a documents nor a text field"

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        if not ctx.resources.distractors:
            return None
        paragraph = ctx.rng.choice(ctx.resources.distractors)
        fields = ctx.fields
        if fields.documents is not None and has_path(source, fields.documents):
            docs = documents_of(source, fields)
            index = self._index(len(docs), ctx)
            docs = [*docs[:index], self._as_document(paragraph, docs, fields), *docs[index:]]
            return FollowUp(
                input=with_path(source, fields.documents, docs),
                note=f"distractor inserted at document {index}: {paragraph[:60]}...",
            )
        assert fields.text is not None
        text = text_of(source, fields)
        at_start = self.position == "start" or (
            self.position == "random" and ctx.rng.random() < 0.5
        )
        new_text = f"{paragraph}\n\n{text}" if at_start else f"{text}\n\n{paragraph}"
        where = "before" if at_start else "after"
        return FollowUp(
            input=with_path(source, fields.text, new_text),
            note=f"distractor added {where} the text: {paragraph[:60]}...",
        )

    def _index(self, n: int, ctx: TransformContext) -> int:
        if self.position == "start":
            return 0
        if self.position == "end":
            return n
        return ctx.rng.randint(0, n)

    @staticmethod
    def _as_document(paragraph: str, docs: list[Any], fields: FieldsConfig) -> Any:
        """Match the shape of existing documents: plain strings or objects with a text key."""
        if docs and isinstance(docs[0], dict):
            template = copy.deepcopy(docs[0])
            template[fields.document_text] = paragraph
            return template
        return paragraph
