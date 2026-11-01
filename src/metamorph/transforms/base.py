"""Transform interface and registry.

A transform turns a source input into one follow-up input. It must be a pure function of
(input, rng, params): the runner seeds the rng per (run seed, relation, seed, variant), so
re-running the same config reproduces identical follow-ups and every call hits the cache.
"""

from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar

from metamorph.config import FieldsConfig
from metamorph.errors import ConfigError
from metamorph.services import Services
from metamorph.types import FollowUp, Input
from metamorph.util import get_path, has_path


@dataclass(frozen=True)
class Resources:
    """Data banks used by transforms. Defaults ship in metamorph/data."""

    distractors: list[str] = field(default_factory=list)
    entity_bank: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, distractors: Path | None = None, entity_bank: Path | None = None) -> Resources:
        data = resources.files("metamorph") / "data"
        distractor_text = (
            distractors.read_text(encoding="utf-8")
            if distractors
            else (data / "distractors.jsonl").read_text(encoding="utf-8")
        )
        bank_text = (
            entity_bank.read_text(encoding="utf-8")
            if entity_bank
            else (data / "entity_bank.json").read_text(encoding="utf-8")
        )
        return cls(
            distractors=[json.loads(line)["text"] for line in distractor_text.splitlines() if line],
            entity_bank=json.loads(bank_text),
        )


@dataclass(frozen=True)
class TransformContext:
    rng: random.Random
    fields: FieldsConfig
    resources: Resources
    variant: int = 0  # which follow-up of this (relation, seed); part of LLM cache keys


class Transform(ABC):
    name: ClassVar[str]
    requires: ClassVar[tuple[str, ...]] = ()  # FieldsConfig roles that must exist in the input

    def missing(self, source: Input, fields: FieldsConfig) -> str | None:
        """Why this transform cannot apply to `source`, or None if it can."""
        for role in self.requires:
            path = getattr(fields, role)
            if path is None:
                return f"fields.{role} is not configured"
            if not has_path(source, path):
                return f"input has no {role} field {path!r}"
        return None

    @abstractmethod
    def apply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        """Return the follow-up, or None when the input offers nothing to change."""

    async def aapply(self, source: Input, ctx: TransformContext) -> FollowUp | None:
        """Async entry point used by the planner; LLM-backed transforms override this."""
        return self.apply(source, ctx)

    def bind(self, services: Services) -> None:  # noqa: B027  (optional hook)
        """Receive run-scoped services; LLM-backed transforms keep the helper model."""


_REGISTRY: dict[str, type[Transform]] = {}


def register[T: type[Transform]](cls: T) -> T:
    _REGISTRY[cls.name] = cls
    return cls


def build_transform(name: str, params: dict[str, Any]) -> Transform:
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise ConfigError(f"unknown transform {name!r} (known: {known})")
    try:
        return _REGISTRY[name](**params)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"bad params for transform {name!r}: {exc}") from exc


def text_of(source: Input, fields: FieldsConfig) -> str:
    assert fields.text is not None
    value = get_path(source, fields.text)
    if not isinstance(value, str):
        raise ConfigError(f"field {fields.text!r} must be a string")
    return value


def documents_of(source: Input, fields: FieldsConfig) -> list[Any]:
    assert fields.documents is not None
    value = get_path(source, fields.documents)
    if not isinstance(value, list):
        raise ConfigError(f"field {fields.documents!r} must be a list")
    return value


def map_strings(value: Any, fn: Callable[[str], str]) -> Any:
    """Apply `fn` to every string leaf of a JSON-like value."""
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [map_strings(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: map_strings(v, fn) for k, v in value.items()}
    return value
