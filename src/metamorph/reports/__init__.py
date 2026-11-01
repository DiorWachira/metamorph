"""Report renderers. Every format renders the same RunReport model."""

from collections.abc import Callable
from typing import Literal

from metamorph.reports.html import render_html
from metamorph.reports.json_report import render_json
from metamorph.reports.junit import render_junit
from metamorph.reports.model import RunReport

ReportFormat = Literal["json", "junit", "html"]

RENDERERS: dict[str, tuple[Callable[[RunReport], str], str]] = {
    "json": (render_json, "report.json"),
    "junit": (render_junit, "junit.xml"),
    "html": (render_html, "report.html"),
}

__all__ = ["RENDERERS", "ReportFormat", "RunReport", "render_html", "render_json", "render_junit"]
