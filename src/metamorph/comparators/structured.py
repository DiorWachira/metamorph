"""Comparators for structured outputs: JSON fields, sets and JSON shape."""

from __future__ import annotations

import re
from typing import Any

from metamorph.comparators.base import (
    Comparator,
    compile_jsonpath,
    parse_json,
    register,
    select,
)
from metamorph.errors import NotComparable
from metamorph.types import Comparison
from metamorph.util import canonical_json


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


@register
class JsonFieldsEqual(Comparator):
    """Score = share of JSONPath fields whose values are equal in both outputs."""

    name = "json_fields_equal"

    def __init__(self, paths: list[str]) -> None:
        if not paths:
            raise ValueError("paths must not be empty")
        self.paths = paths
        self.exprs = [compile_jsonpath(p) for p in paths]

    def compare(self, a: str, b: str) -> Comparison:
        ja, jb = parse_json(a, "source"), parse_json(b, "follow-up")
        differing = [
            path
            for path, expr in zip(self.paths, self.exprs, strict=True)
            if canonical_json(select(expr, ja)) != canonical_json(select(expr, jb))
        ]
        score = 1 - len(differing) / len(self.paths)
        return Comparison(score, "fields equal" if not differing else f"differ: {differing}")


@register
class SetEqual(Comparator):
    """Jaccard similarity of two collections of items (skills, tags, entities...).

    Items come from a JSON array (optionally at `path`); if the output is not JSON, it is split
    on newlines, commas and semicolons, with list bullets stripped.
    """

    name = "set_equal"

    def __init__(self, path: str | None = None, case_sensitive: bool = False) -> None:
        self.path = compile_jsonpath(path) if path else None
        self.case_sensitive = case_sensitive

    def _items(self, text: str, role: str) -> set[str]:
        try:
            data = parse_json(text, role)
        except NotComparable:
            if self.path is not None:
                raise
            raw: list[Any] = [p for p in re.split(r"[\n,;]", text)]
        else:
            if self.path is not None:
                data = select(self.path, data)
                if len(data) == 1 and isinstance(data[0], list):
                    data = data[0]
            if not isinstance(data, list):
                raise NotComparable(f"{role} output is not a list")
            raw = data
        items = {re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(x)).strip() for x in raw}
        items.discard("")
        return items if self.case_sensitive else {i.casefold() for i in items}

    def compare(self, a: str, b: str) -> Comparison:
        sa, sb = self._items(a, "source"), self._items(b, "follow-up")
        score = jaccard(sa, sb)
        missing, extra = sorted(sa - sb), sorted(sb - sa)
        detail = "same items" if score == 1.0 else f"missing {missing}, extra {extra}"
        return Comparison(score, detail)


def shape(value: Any, prefix: str = "$") -> set[str]:
    """Flatten a JSON value into `path:type` entries; list items share one `[*]` path."""
    if isinstance(value, dict):
        entries = {f"{prefix}:object"}
        for key, child in value.items():
            entries |= shape(child, f"{prefix}.{key}")
        return entries
    if isinstance(value, list):
        entries = {f"{prefix}:array"}
        for child in value:
            entries |= shape(child, f"{prefix}[*]")
        return entries
    kind = {bool: "boolean", int: "number", float: "number", str: "string"}.get(type(value), "null")
    return {f"{prefix}:{kind}"}


@register
class JsonSchemaEqual(Comparator):
    """Both outputs must be JSON with the same keys and value types (values may differ)."""

    name = "json_schema_equal"

    def compare(self, a: str, b: str) -> Comparison:
        sa = shape(parse_json(a, "source"))
        try:
            sb = shape(parse_json(b, "follow-up"))
        except NotComparable as exc:
            return Comparison(0.0, str(exc))
        score = jaccard(sa, sb)
        missing, extra = sorted(sa - sb), sorted(sb - sa)
        detail = "same shape" if score == 1.0 else f"missing {missing}, extra {extra}"
        return Comparison(score, detail)
