"""The relation miner: derive app-specific metamorphic relations from requirements.

Following Shin et al. (QUATIC 2024, arXiv:2401.17019), the helper model works in small steps:
find the requirement sentences that constrain inputs and outputs, then rewrite each into a
relation. The relation must be written in Metamorph's own vocabulary (registered transforms and
comparators, enforced by the output schema), so every proposal is executable by construction.
Proposals are validated by actually building them, and a human approves them into
relations/custom.yaml.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from metamorph.collection import Proposal
from metamorph.comparators.base import registry as comparators
from metamorph.config import RelationSpec
from metamorph.errors import ConfigError
from metamorph.llm.base import LLMError, LLMRequest
from metamorph.llm.service import LLMService
from metamorph.relations import Relation, builtin_specs
from metamorph.transforms.base import registry as transforms

MAX_SPEC_CHARS = 60_000
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SYSTEM = (
    "You are a test engineer who derives metamorphic relations for an LLM application from its "
    "requirements. A metamorphic relation says how the output must relate when the input is "
    "changed in a specific way, so it can be checked without knowing the correct output. Work "
    "in two steps: first find the requirement sentences that constrain the relationship between "
    "inputs and outputs, then turn each into a relation using ONLY the transforms and "
    "comparators listed. Prefer relations that would catch real bugs over generic ones. Reply "
    "with JSON only."
)


def _signature(cls: type) -> str:
    params = [
        f"{name}={p.default!r}" if p.default is not inspect.Parameter.empty else name
        for name, p in inspect.signature(cls).parameters.items()
    ]
    return f"({', '.join(params)})" if params else ""


def vocabulary() -> str:
    """The transforms and comparators the model may use, with their parameters and purpose."""

    def doc(cls: type) -> str:
        return (inspect.getdoc(cls) or "").split("\n\n")[0].replace("\n", " ")

    lines = ["Transforms (input -> follow-up input):"]
    lines += [f"- {n}{_signature(c)}: {doc(c)}" for n, c in sorted(transforms().items())]
    lines.append("Comparators (score how much two outputs agree, 0..1):")
    lines += [f"- {n}{_signature(c)}: {doc(c)}" for n, c in sorted(comparators().items())]
    lines.append("Built-in relations that already exist (do not repeat them):")
    lines += [f"- {rid}: {spec['description']}" for rid, spec in builtin_specs().items()]
    return "\n".join(lines)


def schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "kebab-case, unique"},
                        "requirement": {"type": "string", "description": "the sentence, quoted"},
                        "description": {"type": "string"},
                        "transform": {"type": "string", "enum": sorted(transforms())},
                        "transform_params_json": {"type": "string"},
                        "comparator": {"type": "string", "enum": sorted(comparators())},
                        "comparator_params_json": {"type": "string"},
                        "threshold": {"type": ["number", "null"]},
                        "expected": {"type": "string", "enum": ["invariant", "flips"]},
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "requirement",
                        "description",
                        "transform",
                        "transform_params_json",
                        "comparator",
                        "comparator_params_json",
                        "threshold",
                        "expected",
                        "rationale",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["proposals"],
        "additionalProperties": False,
    }


def mine_request(spec_text: str, app_hint: str = "", limit: int = 8) -> LLMRequest:
    """The exact request sent to the helper model (also used to author replay recordings)."""
    hint = f"About the application: {app_hint}\n\n" if app_hint else ""
    prompt = (
        f"{hint}Vocabulary:\n{vocabulary()}\n\n"
        f"Requirements:\n<<<\n{spec_text[:MAX_SPEC_CHARS]}\n>>>\n\n"
        f"Propose at most {limit} relations. For each: quote the requirement sentence it comes "
        "from; choose a transform (use `rewrite` with an `instruction` for app-specific "
        "changes) and a comparator; give their parameters as a JSON object string ('{}' if "
        "none); set `expected` to `flips` only when the change must change the answer; and "
        "explain in one sentence what bug it would catch."
    )
    return LLMRequest(system=SYSTEM, prompt=prompt, schema=schema(), max_tokens=8000)


@dataclass
class MiningResult:
    proposals: list[Proposal] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (id, reason)


def _params(raw: str, what: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} params are not JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{what} params must be an object")
    return value


def validate(raw: dict[str, Any], taken: set[str]) -> RelationSpec:
    """Turn one raw proposal into a RelationSpec that builds, or raise ValueError."""
    rel_id = str(raw.get("id", "")).strip()
    if not _SLUG.match(rel_id):
        raise ValueError("id is not kebab-case")
    if rel_id in taken:
        raise ValueError("id clashes with an existing relation")
    spec = {
        "id": rel_id,
        "description": raw.get("description", ""),
        "requirement": raw.get("requirement") or None,
        "transform": {
            "name": raw.get("transform"),
            "params": _params(raw.get("transform_params_json", ""), "transform"),
        },
        "comparator": {
            "name": raw.get("comparator"),
            "threshold": raw.get("threshold"),
            "params": _params(raw.get("comparator_params_json", ""), "comparator"),
        },
        "expected": raw.get("expected", "invariant"),
    }
    try:
        relation = RelationSpec.model_validate(spec)
        Relation.from_spec(relation)  # builds the transform and comparator: proves it runs
    except (ValidationError, ConfigError) as exc:
        raise ValueError(str(exc).splitlines()[0]) from exc
    return relation


async def mine(
    llm: LLMService,
    spec_text: str,
    source: str,
    taken: set[str],
    app_hint: str = "",
    limit: int = 8,
) -> MiningResult:
    """Ask the helper model for relations and keep only those that validate."""
    if not spec_text.strip():
        raise ConfigError("the requirements file is empty")
    try:
        data = await llm.complete_json("miner", mine_request(spec_text, app_hint, limit))
    except LLMError as exc:
        raise ConfigError(f"mining failed: {exc}") from exc

    result = MiningResult()
    seen = set(taken)
    for raw in data.get("proposals", [])[:limit]:
        if not isinstance(raw, dict):
            continue
        try:
            spec = validate(raw, seen)
        except ValueError as exc:
            result.rejected.append((str(raw.get("id", "?")), str(exc)))
            continue
        seen.add(spec.id)
        rationale = str(raw.get("rationale", ""))
        result.proposals.append(
            Proposal(spec=spec, rationale=rationale, source=source, model=llm.model)
        )
    return result
