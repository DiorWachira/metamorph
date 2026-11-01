"""Word-level diffs for side-by-side views (HTML report and triage UI share this)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Literal

Op = Literal["equal", "delete", "insert"]
Segment = tuple[Op, str]

_TOKEN = re.compile(r"\s+|[^\s]+")


def word_diff(a: str, b: str) -> tuple[list[Segment], list[Segment]]:
    """Diff two texts by words, keeping whitespace. Returns (left, right) segment lists:
    the left side carries `delete` segments and the right side `insert` segments."""
    ta, tb = _TOKEN.findall(a), _TOKEN.findall(b)
    left: list[Segment] = []
    right: list[Segment] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            left.append(("equal", "".join(ta[i1:i2])))
            right.append(("equal", "".join(tb[j1:j2])))
            continue
        if i2 > i1:
            left.append(("delete", "".join(ta[i1:i2])))
        if j2 > j1:
            right.append(("insert", "".join(tb[j1:j2])))
    return _merge(left), _merge(right)


def _merge(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for op, text in segments:
        if merged and merged[-1][0] == op:
            merged[-1] = (op, merged[-1][1] + text)
        elif text:
            merged.append((op, text))
    return merged
