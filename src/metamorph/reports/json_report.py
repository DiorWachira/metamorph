"""JSON report: the full RunReport, for scripts and dashboards."""

from __future__ import annotations

from metamorph.reports.model import RunReport


def render_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)
