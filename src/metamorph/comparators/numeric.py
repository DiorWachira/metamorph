"""Numeric comparator: the numbers in both outputs must match within a tolerance."""

from __future__ import annotations

import math
import re

from metamorph.comparators.base import (
    Comparator,
    compile_jsonpath,
    parse_json,
    register,
    select,
)
from metamorph.errors import NotComparable
from metamorph.types import Comparison

_NUMBER = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def extract_numbers(text: str) -> list[float]:
    return [float(m.group().replace(",", "")) for m in _NUMBER.finditer(text)]


@register
class NumericWithin(Comparator):
    """Score = share of number pairs (in order) within `tol`.

    With `path`, numbers come from that JSONPath in a JSON output; otherwise every number in the
    text is used. `relative: true` makes `tol` a fraction of the source value.
    """

    name = "numeric_within"

    def __init__(self, tol: float = 0.0, relative: bool = False, path: str | None = None) -> None:
        if tol < 0:
            raise ValueError("tol must be >= 0")
        self.tol, self.relative = tol, relative
        self.path = compile_jsonpath(path) if path else None

    def _numbers(self, text: str, role: str) -> list[float]:
        if self.path is None:
            return extract_numbers(text)
        values = select(self.path, parse_json(text, role))
        try:
            return [float(v) for v in values]
        except (TypeError, ValueError) as exc:
            raise NotComparable(f"{role} value at path is not numeric: {values!r}") from exc

    def _close(self, x: float, y: float) -> bool:
        allowed = self.tol * abs(x) if self.relative else self.tol
        return math.isclose(x, y, abs_tol=allowed + 1e-12)

    def compare(self, a: str, b: str) -> Comparison:
        na, nb = self._numbers(a, "source"), self._numbers(b, "follow-up")
        if not na:
            raise NotComparable("source output contains no numbers")
        if len(na) != len(nb):
            return Comparison(0.0, f"{len(na)} numbers vs {len(nb)}")
        close = sum(self._close(x, y) for x, y in zip(na, nb, strict=True))
        mismatches = [f"{x:g}!={y:g}" for x, y in zip(na, nb, strict=True) if not self._close(x, y)]
        detail = "all numbers match" if not mismatches else "mismatch: " + ", ".join(mismatches)
        return Comparison(close / len(na), detail)
