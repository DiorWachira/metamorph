"""Surface-level text perturbations: typos and whitespace/casing noise."""

from __future__ import annotations

import random
import re

from metamorph.transforms.base import Transform, TransformContext, register, text_of
from metamorph.types import FollowUp, Input
from metamorph.util import with_path

_QWERTY_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_NEIGHBOURS: dict[str, str] = {}
for _row in _QWERTY_ROWS:
    for _i, _ch in enumerate(_row):
        _NEIGHBOURS[_ch] = _row[max(0, _i - 1) : _i] + _row[_i + 1 : _i + 2]

# Letters-only words of 4+ characters. Short words, numbers and identifiers are left alone,
# because a typo in "not" or "2019" changes meaning rather than spelling.
_WORD = re.compile(r"\b[^\W\d_]{4,}\b")


def misspell(word: str, rng: random.Random) -> str:
    """One realistic typo inside the word, never touching its first letter."""
    i = rng.randrange(1, len(word) - 1)
    op = rng.choice(("swap", "drop", "double", "neighbour"))
    if op == "swap" and word[i] != word[i + 1]:
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    if op == "drop":
        return word[:i] + word[i + 1 :]
    if op == "double":
        return word[:i] + word[i] + word[i:]
    lower = word[i].lower()
    if lower not in _NEIGHBOURS:
        return word[:i] + word[i] + word[i:]
    replacement = rng.choice(_NEIGHBOURS[lower])
    if word[i].isupper():
        replacement = replacement.upper()
    return word[:i] + replacement + word[i + 1 :]


def add_typos(text: str, rate: float, rng: random.Random) -> str:
    """Misspell each eligible word with probability `rate`; at least one if any are eligible."""
    words = list(_WORD.finditer(text))
    if rate <= 0 or not words:
        return text
    chosen = {m.start() for m in words if rng.random() < rate}
    if not chosen:
        chosen = {rng.choice(words).start()}
    return _WORD.sub(lambda m: misspell(m.group(), rng) if m.start() in chosen else m.group(), text)


@register
class Typos(Transform):
    """Introduce keyboard typos at a per-word rate."""

    name = "typos"
    requires = ("text",)

    def __init__(self, rate: float = 0.1) -> None:
        if not 0 <= rate <= 1:
            raise ValueError("rate must be between 0 and 1")
        self.rate = rate

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        assert ctx.fields.text is not None
        text = text_of(source, ctx.fields)
        noisy = add_typos(text, self.rate, ctx.rng)
        if noisy == text:
            return None
        return FollowUp(
            input=with_path(source, ctx.fields.text, noisy),
            note=f"typos at rate {self.rate}: {noisy!r}",
        )


def _lower_first(text: str, rng: random.Random) -> str:
    return text[:1].lower() + text[1:]


def _double_spaces(text: str, rng: random.Random) -> str:
    return re.sub(r" ", lambda _: "  " if rng.random() < 0.5 else " ", text)


def _pad(text: str, rng: random.Random) -> str:
    return f"  {text}\n"


def _toggle_final_punctuation(text: str, rng: random.Random) -> str:
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".?!":
        return stripped[:-1]
    return stripped + "."


_NOISE_OPS = (_lower_first, _double_spaces, _pad, _toggle_final_punctuation)


@register
class SurfaceNoise(Transform):
    """Meaning-preserving formatting noise: casing, spacing, padding, trailing punctuation."""

    name = "surface_noise"
    requires = ("text",)

    def __init__(self, ops: int = 2) -> None:
        if not 1 <= ops <= len(_NOISE_OPS):
            raise ValueError(f"ops must be between 1 and {len(_NOISE_OPS)}")
        self.ops = ops

    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        assert ctx.fields.text is not None
        text = text_of(source, ctx.fields)
        if not text.strip():
            return None
        chosen = ctx.rng.sample(_NOISE_OPS, self.ops)
        noisy = text
        for op in chosen:
            noisy = op(noisy, ctx.rng)
        if noisy == text:
            noisy = _pad(text, ctx.rng)
        names = ", ".join(op.__name__.strip("_").replace("_", " ") for op in chosen)
        return FollowUp(input=with_path(source, ctx.fields.text, noisy), note=f"noise: {names}")
