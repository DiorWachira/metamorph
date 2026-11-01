"""LLM provider interface, used by LLM-powered transforms and comparators (not by targets)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from metamorph.errors import MetamorphError
from metamorph.util import canonical_json, sha256


class LLMError(MetamorphError):
    """The helper LLM failed or declined; the affected case is skipped, the run continues."""


@dataclass(frozen=True)
class LLMRequest:
    system: str
    prompt: str
    schema: dict[str, Any] | None = None  # JSON schema for structured output
    max_tokens: int = 2048

    def fingerprint(self) -> str:
        return sha256(self.system, self.prompt, canonical_json(self.schema))


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    model: str

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResult:
        """Raise LLMError on refusals or unusable responses."""

    async def aclose(self) -> None:  # noqa: B027  (optional hook)
        """Release network resources."""


def per_mtok(tokens_in: int, tokens_out: int, price_in: float, price_out: float) -> float:
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
