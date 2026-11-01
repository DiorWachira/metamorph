"""Call a Python function in-process. Sync functions run in a worker thread."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from metamorph.adapters.base import OutputExtractor, Target, TargetResponse
from metamorph.config import PythonTargetConfig
from metamorph.errors import ConfigError, TargetError
from metamorph.types import Input
from metamorph.util import canonical_json, sha256


def import_callable(spec: str, base_dir: Path) -> Callable[..., Any]:
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ConfigError(f"callable must look like 'package.module:function', got {spec!r}")
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"cannot import {module_name!r}: {exc}") from exc
    fn = getattr(module, attr, None)
    if not callable(fn):
        raise ConfigError(f"{spec!r} is not a callable")
    return cast(Callable[..., Any], fn)


class PythonTarget(Target):
    def __init__(self, config: PythonTargetConfig, base_dir: Path) -> None:
        self.config = config
        self.fn = import_callable(config.callable, base_dir)
        self.extract = OutputExtractor(config.output_path)

    @property
    def fingerprint(self) -> str:
        return sha256(canonical_json(self.config.model_dump()))

    async def call(self, payload: Input) -> TargetResponse:
        try:
            if inspect.iscoroutinefunction(self.fn):
                result = await self.fn(payload)
            else:
                result = await asyncio.to_thread(self.fn, payload)
        except Exception as exc:
            raise TargetError(f"{type(exc).__name__}: {exc}") from exc
        return TargetResponse(text=self.extract(result))
