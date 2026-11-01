"""Run-scoped services that transforms and comparators can bind to (currently the helper LLM)."""

from __future__ import annotations

from dataclasses import dataclass

from metamorph.errors import ConfigError
from metamorph.llm.service import LLMService


@dataclass(frozen=True)
class Services:
    llm: LLMService | None = None

    def require_llm(self, component: str) -> LLMService:
        if self.llm is None:
            raise ConfigError(
                f"{component} needs a helper model: add an `llm:` section to metamorph.yaml"
            )
        return self.llm
