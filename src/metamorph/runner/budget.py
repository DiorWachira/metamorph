"""A per-run spending limit shared by target calls and helper-LLM calls.

The budget is checked before each call starts, so a run stops gracefully: in-flight calls finish,
nothing new starts, and unrun cases are reported as skipped. Overshoot is bounded by the calls
already in flight (at most `run.concurrency`).
"""

from __future__ import annotations

from metamorph.errors import MetamorphError


class BudgetExhausted(MetamorphError):
    """No new paid calls may start in this run."""


class Budget:
    def __init__(self, limit_usd: float | None = None) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = 0.0
        self.tripped = False  # set once something was actually refused for budget reasons

    @property
    def exhausted(self) -> bool:
        return self.limit_usd is not None and self.spent_usd >= self.limit_usd

    def check(self) -> None:
        if self.exhausted:
            self.tripped = True
            raise BudgetExhausted(f"budget of ${self.limit_usd:.2f} exhausted")

    def charge(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd
