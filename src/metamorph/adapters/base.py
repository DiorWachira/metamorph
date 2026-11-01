"""Target adapter interface: input dict in, response text out."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from metamorph.comparators.base import compile_jsonpath, select
from metamorph.errors import TargetError
from metamorph.types import Input
from metamorph.util import output_to_text


@dataclass(frozen=True)
class TargetResponse:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float = 0.0


class Target(ABC):
    @property
    @abstractmethod
    def fingerprint(self) -> str:
        """Everything that identifies this target's behaviour, for cache keys."""

    @abstractmethod
    async def call(self, payload: Input) -> TargetResponse:
        """Raise RetryableTargetError for transient failures, TargetError for the rest."""

    async def aclose(self) -> None:  # noqa: B027  (optional hook)
        """Release resources such as HTTP connection pools."""


class OutputExtractor:
    """Pull the answer out of a structured response with an optional JSONPath."""

    def __init__(self, path: str | None) -> None:
        self.path = path
        self.expr = compile_jsonpath(path) if path else None

    def __call__(self, value: Any) -> str:
        if self.expr is None:
            return output_to_text(value)
        matches = select(self.expr, value)
        if not matches:
            raise TargetError(f"output_path {self.path} matched nothing in the response")
        return output_to_text(matches[0] if len(matches) == 1 else matches)
