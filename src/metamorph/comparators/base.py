"""Comparator interface and registry.

A comparator scores how much two outputs agree, from 0.0 to 1.0. Scores (rather than booleans)
let the judge compare a follow-up's agreement against the target's own self-agreement.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from jsonpath_ng.ext.parser import parse as parse_jsonpath

from metamorph.errors import ConfigError, NotComparable
from metamorph.services import Services
from metamorph.types import Comparison


class Comparator(ABC):
    name: ClassVar[str]
    default_threshold: ClassVar[float] = 1.0

    @abstractmethod
    def compare(self, a: str, b: str) -> Comparison:
        """Score agreement. Raise NotComparable when the pair cannot be judged."""

    async def acompare(self, a: str, b: str) -> Comparison:
        """Async entry point used by the runner; LLM-backed comparators override this."""
        return self.compare(a, b)

    def bind(self, services: Services) -> None:  # noqa: B027  (optional hook)
        """Receive run-scoped services; LLM-backed comparators keep the helper model."""


_REGISTRY: dict[str, type[Comparator]] = {}


def registry() -> dict[str, type[Comparator]]:
    """Every registered comparator by name (a copy)."""
    return dict(_REGISTRY)


def register[T: type[Comparator]](cls: T) -> T:
    _REGISTRY[cls.name] = cls
    return cls


def build_comparator(name: str, params: dict[str, Any]) -> Comparator:
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise ConfigError(f"unknown comparator {name!r} (known: {known})")
    try:
        return _REGISTRY[name](**params)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"bad params for comparator {name!r}: {exc}") from exc


_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_json(text: str, role: str) -> Any:
    """Parse an output as JSON, tolerating a markdown code fence around it."""
    fenced = _FENCE.match(text)
    try:
        return json.loads(fenced.group(1) if fenced else text)
    except json.JSONDecodeError as exc:
        raise NotComparable(f"{role} output is not JSON: {exc.msg}") from exc


def compile_jsonpath(path: str) -> Any:
    try:
        return parse_jsonpath(path)
    except Exception as exc:  # jsonpath_ng raises several unrelated exception types
        raise ConfigError(f"invalid JSONPath {path!r}: {exc}") from exc


def select(expr: Any, data: Any) -> list[Any]:
    return [match.value for match in expr.find(data)]
