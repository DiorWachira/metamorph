"""Target adapters."""

from pathlib import Path

from metamorph.adapters.base import Target, TargetResponse
from metamorph.adapters.http import HttpTarget
from metamorph.adapters.openai_compatible import OpenAICompatibleTarget
from metamorph.adapters.python import PythonTarget
from metamorph.config import HttpTargetConfig, OpenAICompatibleTargetConfig, PythonTargetConfig


def build_target(
    config: HttpTargetConfig | PythonTargetConfig | OpenAICompatibleTargetConfig, base_dir: Path
) -> Target:
    if isinstance(config, HttpTargetConfig):
        return HttpTarget(config)
    if isinstance(config, OpenAICompatibleTargetConfig):
        return OpenAICompatibleTarget(config, base_dir)
    return PythonTarget(config, base_dir)


__all__ = [
    "HttpTarget",
    "OpenAICompatibleTarget",
    "PythonTarget",
    "Target",
    "TargetResponse",
    "build_target",
]
