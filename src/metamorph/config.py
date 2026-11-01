"""metamorph.yaml schema and loading. Relative paths resolve against the config file's folder."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from metamorph.errors import ConfigError
from metamorph.types import Expectation, Mode
from metamorph.util import expand_env

DEFAULT_CONFIG_NAME = "metamorph.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HttpTargetConfig(_Strict):
    type: Literal["http"]
    url: str
    method: Literal["GET", "POST", "PUT"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    output_path: str | None = None  # JSONPath into the response body, e.g. $.answer
    timeout_s: float = 30.0
    version: str | None = None  # bump to invalidate cached responses by hand


class PythonTargetConfig(_Strict):
    type: Literal["python"]
    callable: str  # "package.module:function"
    output_path: str | None = None
    version: str | None = None


class OpenAICompatibleTargetConfig(_Strict):
    """A prompt-only app: a system prompt plus a templated user message on a chat endpoint."""

    type: Literal["openai_compatible"]
    model: str
    base_url: str = "http://localhost:11434/v1"  # Ollama by default
    api_key_env: str | None = None
    system_prompt_file: Path
    user_template: str = "{text}"  # formatted with the seed input's fields
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    timeout_s: float = 120.0
    version: str | None = None


TargetConfig = Annotated[
    HttpTargetConfig | PythonTargetConfig | OpenAICompatibleTargetConfig,
    Field(discriminator="type"),
]


class LLMConfig(_Strict):
    """The helper model used by LLM transforms (paraphrase, Swahili, Sheng...) and judges."""

    provider: Literal["anthropic", "openai_compatible", "replay"] = "anthropic"
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    base_url: str | None = None  # openai_compatible only
    api_key_env: str | None = None
    input_cost_per_mtok: float = 0.0  # openai_compatible only; Anthropic prices are built in
    output_cost_per_mtok: float = 0.0
    recordings: Path | None = None  # replay: file of recorded calls
    record_to: Path | None = None  # append every live call here, for later replay
    concurrency: int = Field(default=4, ge=1)


class FieldsConfig(_Strict):
    """Where transforms find things in a seed input, as dotted paths."""

    text: str | None = None  # the main natural-language field (question, prompt, CV text)
    documents: str | None = None  # a list of retrieved documents, for RAG relations
    document_text: str = "text"  # key holding the text when documents are objects


class RunConfig(_Strict):
    seed: int = 0
    samples: int = Field(default=1, ge=1)  # k calls per source input for the self-variance baseline
    margin: float = Field(default=0.05, ge=0.0)
    concurrency: int = Field(default=8, ge=1)
    retries: int = Field(default=3, ge=0)
    backoff_s: float = Field(default=0.5, ge=0.0)
    budget_usd: float | None = Field(default=None, gt=0.0)  # stop starting paid calls beyond this


class GateConfig(_Strict):
    max_blocking_violations: int = Field(default=0, ge=0)
    max_blocking_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    max_error_rate: float = Field(default=0.1, ge=0.0, le=1.0)


class CacheConfig(_Strict):
    enabled: bool = True
    # Include the git HEAD and working-tree diff in cache keys so code changes re-call the target.
    invalidate_on_code_change: bool = True


class ResourcesConfig(_Strict):
    distractors: Path | None = None
    entity_bank: Path | None = None


class TransformSpec(_Strict):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class ComparatorSpec(_Strict):
    name: str
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)


class RelationSpec(_Strict):
    id: str
    description: str
    transform: TransformSpec
    comparator: ComparatorSpec
    expected: Expectation = Expectation.INVARIANT
    tags: list[str] = Field(default_factory=list)  # applies to seeds sharing a tag; empty = all
    # None = learned from triage precision (relation_stats), defaulting to WARNING.
    mode: Mode | None = None
    followups: int = Field(default=1, ge=1)
    # The requirement sentence a mined relation was derived from (provenance for reviewers).
    requirement: str | None = None


class Config(_Strict):
    target: TargetConfig
    seeds: Path
    fields: FieldsConfig = Field(default_factory=FieldsConfig)
    relations: list[str | dict[str, Any]] = Field(min_length=1)
    run: RunConfig = Field(default_factory=RunConfig)
    gate: GateConfig = Field(default_factory=GateConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    llm: LLMConfig | None = None
    # Relations approved from the miner (enabled automatically) and modes learned by triage;
    # both are committed with the repo so CI sees them.
    custom_relations: Path = Path("relations/custom.yaml")
    learned_modes: Path = Path("relations/learned.yaml")
    storage_dir: Path = Path(".metamorph")

    base_dir: Path = Field(default=Path("."), exclude=True)
    # The YAML as written, before ${VAR} expansion: safe to store in run snapshots.
    snapshot: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.base_dir / path).resolve()


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"config file not found: {path} (run `metamorph init` to create one)")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    try:
        config = Config.model_validate(expand_env(raw))
    except ValidationError as exc:
        raise ConfigError(f"invalid config {path}:\n{exc}") from exc
    config.base_dir = path.resolve().parent
    config.snapshot = raw
    return config
