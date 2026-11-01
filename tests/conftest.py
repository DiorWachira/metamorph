from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

from metamorph.config import FieldsConfig
from metamorph.transforms import Resources, TransformContext

sys.path.insert(0, str(Path(__file__).parent))

# Shared CI runners are slow and noisy; time-based health checks would only add flakiness.
settings.register_profile("default", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("default")


@pytest.fixture(scope="session")
def resources() -> Resources:
    return Resources.load()


@pytest.fixture
def fields() -> FieldsConfig:
    return FieldsConfig(text="question", documents="documents")


@pytest.fixture
def ctx(fields: FieldsConfig, resources: Resources) -> TransformContext:
    return TransformContext(rng=random.Random(42), fields=fields, resources=resources)
