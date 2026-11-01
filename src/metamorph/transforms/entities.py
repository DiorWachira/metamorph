"""Swap names from the entity bank for others of the same kind, consistently across the input."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from metamorph.transforms.base import Transform, TransformContext, map_strings, register
from metamorph.types import FollowUp, Input


def _replacer(mapping: dict[str, str]) -> Callable[[str], str]:
    """Simultaneous whole-word replacement, so A->B and B->A never chain."""
    if not mapping:
        return lambda text: text
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")\b"
    )
    return lambda text: pattern.sub(lambda m: mapping[m.group()], text)


@register
class SwapEntities(Transform):
    """Replace every bank entity found in the input with an unused one of the same category.

    The reverse mapping is applied to outputs before comparison, so an answer that correctly
    mentions the new name still counts as agreeing with the original.
    """

    name = "swap_entities"

    def __init__(self, categories: list[str] | None = None) -> None:
        self.categories = categories or ["person"]

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        haystack = json.dumps(source, ensure_ascii=False)
        mapping: dict[str, str] = {}
        for category in self.categories:
            bank = ctx.resources.entity_bank.get(category, [])
            present = [n for n in bank if re.search(rf"\b{re.escape(n)}\b", haystack)]
            unused = [n for n in bank if n not in present and n not in mapping.values()]
            ctx.rng.shuffle(unused)
            for name in present:
                if not unused:
                    break
                mapping[name] = unused.pop()
        if not mapping:
            return None
        forward = _replacer(mapping)
        backward = _replacer({new: old for old, new in mapping.items()})
        pairs = ", ".join(f"{old} -> {new}" for old, new in mapping.items())
        return FollowUp(
            input=map_strings(source, forward),
            note=f"entities swapped: {pairs}",
            normalize=backward,
        )
