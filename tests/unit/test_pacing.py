import asyncio

import pytest

from metamorph.adapters.python import PythonTarget
from metamorph.config import PythonTargetConfig
from metamorph.errors import RetryableTargetError, TargetError
from metamorph.runner.pacing import RateLimiter, limiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def test_calls_are_spaced_evenly() -> None:
    time = FakeTime()
    pace = RateLimiter(30, clock=time.clock, sleep=time.sleep)  # one every 2 seconds

    async def three_at_once() -> None:
        await asyncio.gather(pace.wait(), pace.wait(), pace.wait())

    asyncio.run(three_at_once())
    assert time.sleeps == [pytest.approx(2.0), pytest.approx(4.0)]  # the first goes straight away


def test_time_already_passed_counts_towards_the_gap() -> None:
    time = FakeTime()
    pace = RateLimiter(30, clock=time.clock, sleep=time.sleep)
    asyncio.run(pace.wait())
    time.now += 5.0
    asyncio.run(pace.wait())
    assert time.sleeps == []


def test_no_limit_means_no_limiter() -> None:
    assert limiter(None) is None
    assert limiter(10) is not None


def test_a_python_target_can_ask_to_be_retried(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "busy_app.py").write_text(
        "from metamorph.errors import RetryableTargetError\n"
        "def busy(payload):\n"
        "    raise RetryableTargetError('busy', retry_after=7.0)\n"
        "def broken(payload):\n"
        "    raise ValueError('no')\n",
        encoding="utf-8",
    )
    busy = PythonTarget(PythonTargetConfig(type="python", callable="busy_app:busy"), tmp_path)
    with pytest.raises(RetryableTargetError) as caught:
        asyncio.run(busy.call({}))
    assert caught.value.retry_after == 7.0

    broken = PythonTarget(PythonTargetConfig(type="python", callable="busy_app:broken"), tmp_path)
    with pytest.raises(TargetError) as failed:
        asyncio.run(broken.call({}))
    assert not isinstance(failed.value, RetryableTargetError)
