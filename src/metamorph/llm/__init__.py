"""Helper LLMs for LLM-powered transforms and comparators."""

from __future__ import annotations

import os
from pathlib import Path

from metamorph.config import LLMConfig
from metamorph.errors import ConfigError
from metamorph.llm.base import LLMError, LLMProvider, LLMRequest, LLMResult
from metamorph.llm.service import LLMService


def build_provider(config: LLMConfig, base_dir: Path) -> LLMProvider:
    api_key = os.environ.get(config.api_key_env) if config.api_key_env else None
    if config.api_key_env and not api_key:
        raise ConfigError(f"llm.api_key_env: environment variable {config.api_key_env} is not set")
    match config.provider:
        case "anthropic":
            from metamorph.llm.claude import AnthropicProvider

            return AnthropicProvider(config.model, config.effort, api_key)
        case "openai_compatible":
            from metamorph.llm.openai_compatible import OLLAMA_URL, OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                config.model,
                config.base_url or OLLAMA_URL,
                api_key,
                config.input_cost_per_mtok,
                config.output_cost_per_mtok,
            )
        case "replay":
            from metamorph.llm.replay import ReplayProvider

            if config.recordings is None:
                raise ConfigError("llm.provider replay needs llm.recordings")
            return ReplayProvider((base_dir / config.recordings).resolve())


__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMService",
    "build_provider",
]
