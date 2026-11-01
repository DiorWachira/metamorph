"""Measure what the self-variance baseline buys on this noisy target, against known ground truth.

The extractor is simulated, so we know the truth: a reported violation is a TRUE bug when the
noise-free extractor really answers source and follow-up differently, and a FALSE alarm when the
difference is only sampling noise. We run the suite with k=1 (naive) and k=3 (baseline) over
several run seeds and count both.

    python measure.py            # prints a markdown table (used in the README)
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cv_app import extract_skills

from metamorph.comparators.structured import jaccard
from metamorph.config import load_config
from metamorph.suite import RunOptions, run_suite

HERE = Path(__file__).parent
RUN_SEEDS = range(5)
THRESHOLD = 0.8


@dataclass
class Tally:
    violations: int = 0
    true_bugs: int = 0
    real_bugs_present: int = 0
    cases: int = 0

    @property
    def false_alarms(self) -> int:
        return self.violations - self.true_bugs

    @property
    def precision(self) -> float:
        return self.true_bugs / self.violations if self.violations else 1.0

    @property
    def recall(self) -> float:
        return self.true_bugs / self.real_bugs_present if self.real_bugs_present else 1.0


def really_differs(source_cv: str, followup_cv: str, relation_id: str) -> bool:
    a = {s.casefold() for s in extract_skills(source_cv)}
    b = {s.casefold() for s in extract_skills(followup_cv)}
    if relation_id == "json-schema-stability":
        return bool(a) != bool(b)  # the shape changes only when the list empties out
    return jaccard(a, b) < THRESHOLD


async def tally(samples: int) -> Tally:
    total = Tally()
    for run_seed in RUN_SEEDS:
        config = load_config(HERE / "metamorph.yaml")
        config.run.samples = samples
        config.run.seed = run_seed
        with tempfile.TemporaryDirectory() as tmp:
            config.storage_dir = Path(tmp)
            report = await run_suite(config, RunOptions(use_cache=False))
        for case in report.cases:
            truth = really_differs(
                case.source_input["cv_text"], case.followup_input["cv_text"], case.relation_id
            )
            total.cases += 1
            total.real_bugs_present += truth
            if case.status == "violation":
                total.violations += 1
                total.true_bugs += truth
    return total


async def main() -> None:
    naive, baselined = await tally(1), await tally(3)
    print("| | k = 1 (naive) | k = 3 (self-variance baseline) |")
    print("|---|---:|---:|")
    print(f"| cases | {naive.cases} | {baselined.cases} |")
    print(f"| violations reported | {naive.violations} | {baselined.violations} |")
    print(f"| true bugs among them | {naive.true_bugs} | {baselined.true_bugs} |")
    print(f"| false alarms | {naive.false_alarms} | {baselined.false_alarms} |")
    print(f"| precision | {naive.precision:.0%} | {baselined.precision:.0%} |")
    print(f"| recall of real bugs | {naive.recall:.0%} | {baselined.recall:.0%} |")


if __name__ == "__main__":
    asyncio.run(main())
