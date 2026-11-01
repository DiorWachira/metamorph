"""Number formatting: 1000 <-> 1,000. The value is unchanged, so the answer should be too."""

from __future__ import annotations

import re
from typing import Literal

from metamorph.transforms.base import Transform, TransformContext, map_strings, register
from metamorph.types import FollowUp, Input
from metamorph.util import get_path, with_path

# A bare integer of 4+ digits that is not part of a word, decimal tail or grouped number,
# and does not start with 0 (phone numbers, IDs).
_PLAIN = re.compile(r"(?<![\w.,])[1-9]\d{3,}(?![\w,])")
# An integer already grouped with commas: 1,000 or 12,345,678.
_GROUPED = re.compile(r"(?<![\w.,])[1-9]\d{0,2}(?:,\d{3})+(?![\w,])")
_SEPARATOR_IN_OUTPUT = re.compile(r"(?<=\d),(?=\d{3}\b)")


def _looks_like_year(digits: str) -> bool:
    return len(digits) == 4 and 1800 <= int(digits) <= 2199


def group_thousands(text: str, skip_years: bool = True) -> str:
    def fmt(match: re.Match[str]) -> str:
        digits = match.group()
        if skip_years and _looks_like_year(digits):
            return digits
        return f"{int(digits):,}"

    return _PLAIN.sub(fmt, text)


def ungroup_thousands(text: str) -> str:
    return _GROUPED.sub(lambda m: m.group().replace(",", ""), text)


def canonical_numbers(text: str) -> str:
    """Strip thousands separators so '1,000' and '1000' in outputs compare equal."""
    return _SEPARATOR_IN_OUTPUT.sub("", text)


@register
class NumberFormat(Transform):
    """Rewrite integers with or without thousands separators.

    `style: auto` removes separators if the input already uses them, otherwise adds them.
    Four-digit years are left alone by default because "1,963" is not a year anyone writes.
    """

    name = "number_format"
    requires = ("text",)

    def __init__(
        self,
        style: Literal["auto", "grouped", "plain"] = "auto",
        scope: Literal["text", "all"] = "text",
        skip_years: bool = True,
    ) -> None:
        if style not in ("auto", "grouped", "plain"):
            raise ValueError("style must be auto, grouped or plain")
        if scope not in ("text", "all"):
            raise ValueError("scope must be text or all")
        self.style, self.scope, self.skip_years = style, scope, skip_years

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        fields = ctx.fields
        assert fields.text is not None
        paths = [fields.text]
        if self.scope == "all" and fields.documents is not None:
            paths.append(fields.documents)

        style = self.style
        if style == "auto":
            sample = " ".join(str(get_path(source, p, "")) for p in paths)
            style = "plain" if _GROUPED.search(sample) else "grouped"

        def rewrite(s: str) -> str:
            return (
                group_thousands(s, self.skip_years) if style == "grouped" else ungroup_thousands(s)
            )

        result = source
        for path in paths:
            result = with_path(result, path, map_strings(get_path(result, path), rewrite))
        if result == source:
            return None
        return FollowUp(
            input=result,
            note=f"numbers rewritten in {style} style",
            normalize=canonical_numbers,
        )
