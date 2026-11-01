"""Markdown report for pull-request comments and the GitHub job summary.

It is short on purpose: the verdict, one row per relation, and the first few blocking
violations with both answers. The full detail lives in the HTML/JSON reports.
"""

from __future__ import annotations

from metamorph.reports.model import CaseView, RunReport
from metamorph.types import Mode, Status

MARKER = "<!-- metamorph-report -->"  # lets the GitHub Action update its comment in place
MAX_CASES = 5
MAX_TEXT = 220


def _clip(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= MAX_TEXT else one_line[: MAX_TEXT - 1] + "…"


def _cell(text: str) -> str:
    return _clip(text).replace("|", "\\|") or "∅"


def _verdict(report: RunReport) -> str:
    gate = report.gate
    if gate is None:
        return "⚪ **No gate result**"
    if gate.too_many_errors:
        return "⚪ **Target failing**: " + "; ".join(gate.reasons)
    if gate.passed:
        return "🟢 **Gate passed**"
    return "🔴 **Gate failed**: " + "; ".join(gate.reasons)


def _case(c: CaseView) -> list[str]:
    source = c.source_outputs[0].text if c.source_outputs else ""
    return [
        f"<details><summary><code>{c.relation_id}</code> on <code>{c.seed_id}</code>: "
        f"{_clip(c.detail)}</summary>",
        "",
        f"*Transform:* {_clip(c.followup_note)}",
        "",
        "| source answer | follow-up answer |",
        "|---|---|",
        f"| {_cell(source)} | {_cell(c.followup_output.text)} |",
        "",
        "</details>",
    ]


def render_markdown(report: RunReport) -> str:
    effect = report.baseline_effect
    lines = [
        MARKER,
        "### Metamorph",
        "",
        _verdict(report),
        "",
        f"{len(report.cases)} cases · {effect['violations']} violations "
        f"({report.gate.blocking_violations if report.gate else 0} blocking)"
        + (
            f" · {effect['excused']} excused as the app's own noise (k = {report.run.samples})"
            if report.run.samples > 1
            else ""
        )
        + f" · cost ${report.run.total_cost_usd:.4f}",
        "",
        "| relation | mode | cases | violations | excused |",
        "|---|---|---:|---:|---:|",
    ]
    for r in report.relations:
        mode = "**blocking**" if r.mode is Mode.BLOCKING else "warning"
        lines.append(f"| `{r.id}` | {mode} | {r.cases} | {r.violations} | {r.excused} |")

    blocking = [c for c in report.cases if c.status is Status.VIOLATION and c.mode is Mode.BLOCKING]
    warnings = [c for c in report.cases if c.status is Status.VIOLATION and c.mode is Mode.WARNING]
    shown = (blocking + warnings)[:MAX_CASES]
    if shown:
        lines += ["", "#### First violations", ""]
        for c in shown:
            lines += _case(c)
        hidden = len(blocking) + len(warnings) - len(shown)
        if hidden:
            lines += ["", f"…and {hidden} more in the HTML report artifact."]
    lines += ["", f"<sub>Run `{report.run.id}` · no labelled answers were used.</sub>", ""]
    return "\n".join(lines)
