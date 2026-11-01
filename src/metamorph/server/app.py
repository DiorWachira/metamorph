"""Triage server: a JSON API over the run store, plus the built UI.

    metamorph serve            # http://127.0.0.1:8765

Single-user and local by design (no auth): it binds to 127.0.0.1 unless told otherwise.
"""

# No `from __future__ import annotations` here: FastAPI must evaluate the closure-local
# `StoreDep` annotation eagerly to recognise it as a dependency.
import random
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from metamorph.config import Config, FieldsConfig
from metamorph.diff import word_diff
from metamorph.errors import ConfigError, MetamorphError
from metamorph.promotion import MIN_PRECISION, MIN_REVIEWED
from metamorph.relations import builtin_specs, resolve_relations
from metamorph.reports.model import CaseView, RunReport, Triage
from metamorph.storage.repo import RelationStats, RunListItem, Store
from metamorph.suite import open_store
from metamorph.transforms import Resources, TransformContext, build_transform
from metamorph.transforms.llm import LLMRewrite
from metamorph.types import Mode

STATIC = Path(str(resources.files("metamorph.server") / "static"))


class TriageRequest(BaseModel):
    verdict: Triage
    note: str | None = Field(default=None, max_length=2000)


class TriageResponse(BaseModel):
    case: CaseView
    stats: RelationStats


class CaseDetail(BaseModel):
    case: CaseView
    output_diff: dict[str, list[tuple[str, str]]]
    input_diff: dict[str, list[tuple[str, str]]]
    changed_field: str | None
    neighbours: dict[str, int | None]  # previous / next violation in the same run


class RelationEntry(BaseModel):
    id: str
    description: str
    transform: str
    comparator: str
    tags: list[str]
    enabled: bool
    mode: Mode
    mode_source: str
    llm: bool
    stats: RelationStats | None


class RelationsResponse(BaseModel):
    relations: list[RelationEntry]
    min_reviewed: int
    min_precision: float


class LabRequest(BaseModel):
    transform: str
    params: dict[str, Any] = Field(default_factory=dict)
    text: str = Field(max_length=5000)
    documents: list[str] = Field(default_factory=list, max_length=20)
    seed: int = 0


class LabResponse(BaseModel):
    changed: bool
    note: str
    text: str
    documents: list[str]
    diff: dict[str, list[tuple[str, str]]]


class Overview(BaseModel):
    project: str
    target: str
    relations_enabled: int
    runs: int
    latest: RunListItem | None
    reviewed: int
    true_bugs: int
    false_alarms: int


def as_diff(a: str, b: str) -> dict[str, list[tuple[str, str]]]:
    left, right = word_diff(a, b)
    return {"left": list(left), "right": list(right)}


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="Metamorph", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def store() -> Iterator[Store]:
        with open_store(config) as s:
            yield s

    StoreDep = Annotated[Store, Depends(store)]

    def report_or_404(s: Store, run_id: str) -> RunReport:
        resolved = s.latest_run_id() if run_id == "latest" else run_id
        report = s.load_report(resolved) if resolved else None
        if report is None:
            raise HTTPException(404, f"no run {run_id!r}")
        return report

    @app.get("/api/overview")
    def overview(s: StoreDep) -> Overview:
        runs = s.list_runs()
        stats = s.relation_stats()
        return Overview(
            project=config.base_dir.name,
            target=config.target.type,
            relations_enabled=len(config.relations),
            runs=len(runs),
            latest=runs[0] if runs else None,
            reviewed=sum(r.reviewed for r in stats),
            true_bugs=sum(r.true_bugs for r in stats),
            false_alarms=sum(r.false_alarms for r in stats),
        )

    @app.get("/api/runs")
    def runs(s: StoreDep) -> list[RunListItem]:
        return s.list_runs()

    @app.get("/api/runs/{run_id}")
    def run(run_id: str, s: StoreDep) -> RunReport:
        return report_or_404(s, run_id)

    @app.get("/api/cases/{case_id}")
    def case(case_id: int, s: StoreDep) -> CaseDetail:
        found = s.load_case(case_id)
        if found is None:
            raise HTTPException(404, f"no case {case_id}")
        report = report_or_404(s, found.run_id)
        violations = [c.id for c in report.violations]
        idx = violations.index(case_id) if case_id in violations else None
        field, before, after = found.changed_field()
        source_text = found.source_outputs[0].text if found.source_outputs else ""
        return CaseDetail(
            case=found,
            output_diff=as_diff(source_text, found.followup_output.text),
            input_diff=as_diff(before, after),
            changed_field=field,
            neighbours={
                "previous": violations[idx - 1] if idx else None,
                "next": (
                    violations[idx + 1] if idx is not None and idx + 1 < len(violations) else None
                ),
            },
        )

    @app.post("/api/cases/{case_id}/triage")
    def triage(case_id: int, body: TriageRequest, s: StoreDep) -> TriageResponse:
        try:
            stats = s.triage(case_id, body.verdict, body.note)
        except MetamorphError as exc:
            raise HTTPException(400, str(exc)) from exc
        updated = s.load_case(case_id)
        assert updated is not None
        return TriageResponse(case=updated, stats=stats)

    @app.get("/api/relations")
    def relations(s: StoreDep) -> RelationsResponse:
        stats = {r.relation_id: r for r in s.relation_stats()}
        try:
            enabled = {r.id: r for r in resolve_relations(config, learned_modes=s.learned_modes())}
        except ConfigError:
            enabled = {}
        entries = []
        for rel_id, spec in builtin_specs().items():
            params = spec["transform"].get("params", {})
            transform = build_transform(spec["transform"]["name"], params)
            rel = enabled.get(rel_id)
            learned = stats[rel_id].learned_mode if rel_id in stats else None
            entries.append(
                RelationEntry(
                    id=rel_id,
                    description=spec["description"],
                    transform=spec["transform"]["name"],
                    comparator=(rel.spec.comparator.name if rel else spec["comparator"]["name"]),
                    tags=spec.get("tags", []),
                    enabled=rel is not None,
                    mode=rel.mode if rel else (learned or Mode.WARNING),
                    mode_source=rel.mode_source if rel else ("learned" if learned else "default"),
                    llm=isinstance(transform, LLMRewrite),
                    stats=stats.get(rel_id),
                )
            )
        for rel_id, rel in enabled.items():  # custom relations defined only in config
            if rel_id not in builtin_specs():
                entries.append(
                    RelationEntry(
                        id=rel_id,
                        description=rel.spec.description,
                        transform=rel.spec.transform.name,
                        comparator=rel.spec.comparator.name,
                        tags=rel.spec.tags,
                        enabled=True,
                        mode=rel.mode,
                        mode_source=rel.mode_source,
                        llm=isinstance(rel.transform, LLMRewrite),
                        stats=stats.get(rel_id),
                    )
                )
        return RelationsResponse(
            relations=entries, min_reviewed=MIN_REVIEWED, min_precision=MIN_PRECISION
        )

    @app.post("/api/lab/transform")
    def lab(body: LabRequest) -> LabResponse:
        """Preview a deterministic transform on any text: the follow-up a run would generate."""
        try:
            transform = build_transform(body.transform, body.params)
        except ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        if isinstance(transform, LLMRewrite):
            raise HTTPException(400, "the lab previews deterministic transforms only")
        source: dict[str, Any] = {"question": body.text, "documents": body.documents}
        ctx = TransformContext(
            rng=random.Random(body.seed),
            fields=FieldsConfig(text="question", documents="documents"),
            resources=Resources.load(),
        )
        if reason := transform.missing(source, ctx.fields):
            raise HTTPException(400, reason)
        followup = transform.apply(source, ctx)
        if followup is None:
            return LabResponse(
                changed=False,
                note="nothing to change in this input",
                text=body.text,
                documents=body.documents,
                diff=as_diff(body.text, body.text),
            )
        return LabResponse(
            changed=True,
            note=followup.note,
            text=followup.input["question"],
            documents=followup.input["documents"],
            diff=as_diff(body.text, followup.input["question"]),
        )

    mount_ui(app)
    return app


def mount_ui(app: FastAPI) -> None:
    """Serve the built single-page UI, falling back to index.html for client-side routes."""
    index = STATIC / "index.html"
    if not index.exists():

        @app.get("/", include_in_schema=False)
        def missing_ui() -> dict[str, str]:
            return {"detail": "UI not built: run `npm run build` in ui/ (the API is at /api)"}

        return
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (STATIC / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)
