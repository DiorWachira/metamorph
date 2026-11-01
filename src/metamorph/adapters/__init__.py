"""Target adapters."""

from pathlib import Path

from metamorph.adapters.base import Target, TargetResponse
from metamorph.adapters.http import HttpTarget
from metamorph.adapters.python import PythonTarget
from metamorph.config import HttpTargetConfig, PythonTargetConfig


def build_target(config: HttpTargetConfig | PythonTargetConfig, base_dir: Path) -> Target:
    if isinstance(config, HttpTargetConfig):
        return HttpTarget(config)
    return PythonTarget(config, base_dir)


__all__ = ["HttpTarget", "PythonTarget", "Target", "TargetResponse", "build_target"]
