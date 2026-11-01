"""The relation files a project commits next to metamorph.yaml.

    relations/proposed.yaml   relations the miner proposed, awaiting a human decision
    relations/custom.yaml     approved, app-specific relations (enabled automatically)
    relations/learned.yaml    modes learned from triage, so CI applies the trust you earned

All three are plain YAML so they diff well in review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from metamorph.config import Config, RelationSpec
from metamorph.errors import ConfigError, MetamorphError
from metamorph.types import Mode

ProposalStatus = Literal["proposed", "approved", "rejected"]


class Proposal(BaseModel):
    spec: RelationSpec
    rationale: str = ""
    status: ProposalStatus = "proposed"
    source: str = ""  # the requirements file it was mined from
    model: str = ""
    mined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc


def _write_yaml(path: Path, data: Any, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(f"# {header}\n{body}", encoding="utf-8")


# --- approved custom relations ---------------------------------------------------------------


def load_custom(path: Path) -> list[RelationSpec]:
    raw = _read_yaml(path) or []
    if not isinstance(raw, list):
        raise ConfigError(f"{path} must be a list of relations")
    try:
        return [RelationSpec.model_validate(entry) for entry in raw]
    except ValidationError as exc:
        raise ConfigError(f"invalid relation in {path}:\n{exc}") from exc


def save_custom(path: Path, specs: list[RelationSpec]) -> None:
    data = [s.model_dump(mode="json", exclude_none=True, exclude_defaults=False) for s in specs]
    _write_yaml(path, data, "Approved app-specific relations. Edit freely; enabled automatically.")


# --- proposals -------------------------------------------------------------------------------


def proposals_path(config: Config) -> Path:
    return config.resolve(config.custom_relations).with_name("proposed.yaml")


def load_proposals(path: Path) -> list[Proposal]:
    raw = _read_yaml(path) or []
    try:
        return [Proposal.model_validate(entry) for entry in raw]
    except ValidationError as exc:
        raise ConfigError(f"invalid proposal in {path}:\n{exc}") from exc


def save_proposals(path: Path, proposals: list[Proposal]) -> None:
    data = [p.model_dump(mode="json", exclude_none=True) for p in proposals]
    _write_yaml(path, data, "Relations proposed by `metamorph mine`. Approve or reject them.")


def decide(config: Config, ids: list[str], status: Literal["approved", "rejected"]) -> list[str]:
    """Approve (into custom.yaml) or reject proposals by id. Returns the ids decided."""
    path = proposals_path(config)
    proposals = load_proposals(path)
    pending = {p.spec.id: p for p in proposals if p.status == "proposed"}
    unknown = [i for i in ids if i not in pending]
    if unknown:
        raise MetamorphError(f"no pending proposal with id {', '.join(unknown)}")
    for rel_id in ids:
        pending[rel_id].status = status
    if status == "approved":
        custom_path = config.resolve(config.custom_relations)
        custom = load_custom(custom_path)
        existing = {s.id for s in custom}
        custom += [pending[i].spec for i in ids if i not in existing]
        save_custom(custom_path, custom)
    save_proposals(path, proposals)
    return ids


# --- learned modes ---------------------------------------------------------------------------


def load_learned(path: Path) -> dict[str, Mode]:
    raw = _read_yaml(path) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must map relation ids to entries")
    modes: dict[str, Mode] = {}
    for rel_id, entry in raw.items():
        mode = entry.get("mode") if isinstance(entry, dict) else entry
        if mode is not None:
            try:
                modes[str(rel_id)] = Mode(mode)
            except ValueError as exc:
                raise ConfigError(f"{path}: {rel_id} has unknown mode {mode!r}") from exc
    return modes


def save_learned(path: Path, stats: list[Any]) -> None:
    """Write triage statistics (RelationStats) so the learned modes can be committed."""
    data = {
        s.relation_id: {
            "mode": s.learned_mode.value if s.learned_mode else None,
            "precision": None if s.precision is None else round(s.precision, 3),
            "reviewed": s.reviewed,
            "true_bugs": s.true_bugs,
            "false_alarms": s.false_alarms,
        }
        for s in stats
    }
    _write_yaml(path, data, "Modes learned from triage (written by Metamorph). Commit this file.")
