"""Report renderers. Every format renders the same RunReport model."""

from collections.abc import Callable
from typing import Literal

from metamorph.reports.json_report import render_json
from metamorph.reports.junit import render_junit
from metamorph.reports.model import RunReport

ReportFormat = Literal["json", "junit"]

RENDERERS: dict[str, tuple[Callable[[RunReport], str], str]] = {
    "json": (render_json, "report.json"),
    "junit": (render_junit, "junit.xml"),
}

__all__ = ["RENDERERS", "ReportFormat", "RunReport", "render_json", "render_junit"]
