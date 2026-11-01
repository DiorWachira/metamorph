"""Relations: (transform, comparator, expectation) resolved from the catalogue and config."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from metamorph.comparators import Comparator, build_comparator
from metamorph.config import Config, RelationSpec
from metamorph.errors import ConfigError
from metamorph.services import Services
from metamorph.transforms import Transform, build_transform
from metamorph.types import Expectation, Mode, Seed

ModeSource = Literal["config", "learned", "default"]


@dataclass(frozen=True)
class Relation:
    spec: RelationSpec
    transform: Transform
    comparator: Comparator
    threshold: float
    mode: Mode = Mode.WARNING
    # Where the mode came from: pinned in config, learned from triage precision, or the default.
    mode_source: ModeSource = "default"

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def expected(self) -> Expectation:
        return self.spec.expected

    def applies_to(self, seed: Seed) -> bool:
        return not self.spec.tags or bool(seed.tags & set(self.spec.tags))

    def bind(self, services: Services) -> None:
        self.transform.bind(services)
        self.comparator.bind(services)

    @classmethod
    def from_spec(cls, spec: RelationSpec, learned_mode: Mode | None = None) -> Relation:
        comparator = build_comparator(spec.comparator.name, spec.comparator.params)
        threshold = spec.comparator.threshold
        source: ModeSource
        if spec.mode is not None:
            mode, source = spec.mode, "config"
        elif learned_mode is not None:
            mode, source = learned_mode, "learned"
        else:
            mode, source = Mode.WARNING, "default"
        return cls(
            spec=spec,
            transform=build_transform(spec.transform.name, spec.transform.params),
            comparator=comparator,
            threshold=comparator.default_threshold if threshold is None else threshold,
            mode=mode,
            mode_source=source,
        )


def builtin_specs() -> dict[str, dict[str, Any]]:
    text = (resources.files("metamorph.relations") / "builtin.yaml").read_text(encoding="utf-8")
    return {entry["id"]: entry for entry in yaml.safe_load(text)}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            # Switching to a different transform/comparator must not inherit the old params.
            if "name" in value and value["name"] != merged[key].get("name"):
                merged[key] = value
            else:
                merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_relations(
    config: Config,
    only: list[str] | None = None,
    learned_modes: dict[str, Mode] | None = None,
) -> list[Relation]:
    """Build the relations enabled in config, optionally narrowed to the ids in `only`.

    A relation's mode is the one pinned in config, else the one learned from triage
    (`learned_modes`), else WARNING.
    """
    learned_modes = learned_modes or {}
    catalogue = builtin_specs()
    relations: list[Relation] = []
    for entry in config.relations:
        raw = {"id": entry} if isinstance(entry, str) else entry
        rel_id = raw.get("id")
        if not isinstance(rel_id, str):
            raise ConfigError(f"relation entry needs an id: {entry!r}")
        if isinstance(entry, str) and rel_id not in catalogue:
            raise ConfigError(f"unknown relation {rel_id!r} (known: {', '.join(catalogue)})")
        try:
            spec = RelationSpec.model_validate(_merge(catalogue.get(rel_id, {}), raw))
        except ValidationError as exc:
            raise ConfigError(f"invalid relation {rel_id!r}:\n{exc}") from exc
        relations.append(Relation.from_spec(spec, learned_modes.get(rel_id)))

    ids = [r.id for r in relations]
    if len(ids) != len(set(ids)):
        raise ConfigError("a relation is enabled more than once")
    if only:
        unknown = set(only) - set(ids)
        if unknown:
            raise ConfigError(f"--relations names relations not enabled in config: {unknown}")
        relations = [r for r in relations if r.id in only]
    return relations
