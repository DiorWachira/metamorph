"""Exception hierarchy. Anything deriving from MetamorphError maps to CLI exit code 2."""


class MetamorphError(Exception):
    """Base class for expected, user-facing failures."""


class ConfigError(MetamorphError):
    """The configuration, seeds or relation definitions are invalid."""


class TargetError(MetamorphError):
    """The target failed to produce an output."""


class RetryableTargetError(TargetError):
    """A transient target failure (timeout, 429, 5xx) worth retrying.

    `retry_after` carries a server-provided delay in seconds, when one was given.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotComparable(MetamorphError):
    """A comparator cannot judge this pair (e.g. the source output is not JSON)."""
