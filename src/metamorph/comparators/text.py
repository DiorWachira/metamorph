"""Text comparators: exact match and token-overlap F1."""

from __future__ import annotations

import re
from collections import Counter

from metamorph.comparators.base import Comparator, register
from metamorph.types import Comparison

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+")


@register
class Exact(Comparator):
    """1.0 when the outputs are identical after optional case and whitespace normalisation."""

    name = "exact"

    def __init__(self, case_sensitive: bool = False, collapse_whitespace: bool = True) -> None:
        self.case_sensitive = case_sensitive
        self.collapse_whitespace = collapse_whitespace

    def _norm(self, text: str) -> str:
        if self.collapse_whitespace:
            text = _WS.sub(" ", text).strip()
        return text if self.case_sensitive else text.casefold()

    def compare(self, a: str, b: str) -> Comparison:
        same = self._norm(a) == self._norm(b)
        return Comparison(1.0 if same else 0.0, "identical" if same else "outputs differ")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


@register
class TokenF1(Comparator):
    """SQuAD-style token F1: a cheap, model-free similarity for short answers."""

    name = "token_f1"
    default_threshold = 0.8

    def compare(self, a: str, b: str) -> Comparison:
        ta, tb = tokens(a), tokens(b)
        if not ta and not tb:
            return Comparison(1.0, "both empty")
        common = sum((Counter(ta) & Counter(tb)).values())
        if common == 0:
            return Comparison(0.0, "no shared tokens")
        precision, recall = common / len(tb), common / len(ta)
        f1 = 2 * precision * recall / (precision + recall)
        return Comparison(f1, f"token F1 {f1:.2f}")
