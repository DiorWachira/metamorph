"""Static HTML report: one self-contained page per run, styled with the Specimen Cabinet system."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from metamorph.diff import word_diff
from metamorph.reports.model import CaseView, RunReport
from metamorph.types import Status

MAX_PLATES = 200

_env = Environment(
    loader=PackageLoader("metamorph.reports", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def pin_class(case: CaseView) -> str:
    return "st-excused" if case.excused_by_baseline else f"st-{case.status.value}"


def changed_input(case: CaseView) -> tuple[str, str]:
    """The input text to show in the plate: the first top-level field that changed."""
    for key, value in case.followup_input.items():
        if case.source_input.get(key) != value:
            before, after = case.source_input.get(key), value
            if isinstance(before, str) and isinstance(after, str):
                return before, after
            return (
                json.dumps(before, indent=2, ensure_ascii=False),
                json.dumps(after, indent=2, ensure_ascii=False),
            )
    return "", ""


def plate(case: CaseView) -> dict[str, Any]:
    before, after = changed_input(case)
    source_text = case.source_outputs[0].text if case.source_outputs else ""
    out_left, out_right = word_diff(source_text, case.followup_output.text)
    in_left, in_right = word_diff(before, after)
    return {
        "case": case,
        "in_left": in_left,
        "in_right": in_right,
        "out_left": out_left,
        "out_right": out_right,
    }


def render_html(report: RunReport) -> str:
    css = (resources.files("metamorph.design") / "specimen.css").read_text(encoding="utf-8")
    violations = [c for c in report.cases if c.status is Status.VIOLATION]
    violations.sort(key=lambda c: (c.mode.value != "blocking", c.relation_id, c.seed_id))
    by_relation: dict[str, list[CaseView]] = {}
    for case in report.cases:
        by_relation.setdefault(case.relation_id, []).append(case)
    return _env.get_template("report.html.j2").render(
        report=report,
        css=css,
        plates=[plate(c) for c in violations[:MAX_PLATES]],
        hidden_plates=max(0, len(violations) - MAX_PLATES),
        by_relation=by_relation,
        pin_class=pin_class,
        transforms={r.id: r.transform for r in report.relations},
    )
