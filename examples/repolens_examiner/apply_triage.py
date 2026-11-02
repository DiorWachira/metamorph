"""Record the case study's determinations on the latest run, by one written rule.

The rule: RepoLens documents its offline mode as answering three kinds of question (a plan, what to
fix first, explain this line) and sends free-form questions to Gemini. So:

- true defect: the follow-up is still recognisably one of those documented questions, misspelled.
- false alarm: the follow-up is free-form rewording, which the mode says it does not handle.

These are the author's provisional determinations, not an independent review. Overrule any of them
in the cabinet (`metamorph triage`), which simply records a newer verdict.
"""

from collections import Counter
from pathlib import Path

from metamorph.config import load_config
from metamorph.reports.model import Triage
from metamorph.suite import open_store
from metamorph.types import Status

NOTE = {
    "typo-robustness": "A misspelled documented question falls through to the fallback answer.",
    "paraphrase-invariance": "Free-form rewording: outside the offline mode's documented scope.",
    "code-switch-invariance": "Free-form rewording: outside the offline mode's documented scope.",
}


def main() -> None:
    with open_store(load_config(Path("metamorph.yaml"))) as store:
        run_id = store.latest_run_id()
        report = store.load_report(run_id) if run_id else None
        if report is None:
            raise SystemExit("No run stored yet: run `metamorph run` first.")
        tally: Counter[tuple[str, str]] = Counter()
        for case in report.cases:
            if case.status != Status.VIOLATION:
                continue
            verdict: Triage = "true_bug" if case.relation_id == "typo-robustness" else "false_alarm"
            store.triage(case.id, verdict, f"Provisional. {NOTE[case.relation_id]}")
            tally[(case.relation_id, verdict)] += 1
    for (relation, verdict), count in sorted(tally.items()):
        print(f"{relation:26} {verdict:12} {count}")


if __name__ == "__main__":
    main()
