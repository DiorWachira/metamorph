"""Persistence for runs and their cases, and loading them back as a RunReport."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, insert, select, update

from metamorph.reports.model import (
    CaseView,
    GateResult,
    OutputView,
    RelationSummary,
    RunReport,
    RunView,
    SkipView,
)
from metamorph.runner.engine import CaseResult
from metamorph.storage.schema import cases, metadata, outputs, runs, verdicts
from metamorph.types import Mode, Status, TargetOutput
from metamorph.util import canonical_json


def sqlite_url(storage_dir: Path) -> str:
    storage_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(storage_dir / 'metamorph.db').as_posix()}"


def _output_row(case_id: int, role: str, idx: int, out: TargetOutput) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "role": role,
        "sample_idx": idx,
        "text": out.text,
        "latency_ms": out.latency_ms,
        "tokens_in": out.tokens_in,
        "tokens_out": out.tokens_out,
        "cost_usd": out.cost_usd,
        "cached": out.cached,
        "error": out.error,
    }


class Store:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url)
        metadata.create_all(self.engine)

    def create_run(self, run_id: str, git_sha: str | None, config: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(runs).values(
                    id=run_id,
                    started_at=datetime.now(UTC),
                    git_sha=git_sha,
                    config_json=canonical_json(config),
                    total_cost_usd=0.0,
                    status="running",
                )
            )

    def save_results(self, run_id: str, results: list[CaseResult]) -> None:
        with self.engine.begin() as conn:
            for r in results:
                case_id: int = conn.execute(
                    insert(cases)
                    .values(
                        run_id=run_id,
                        relation_id=r.relation.id,
                        seed_id=r.seed.id,
                        variant=r.variant,
                        source_input_json=canonical_json(r.seed.input),
                        followup_input_json=canonical_json(r.followup.input),
                        followup_note=r.followup.note,
                        tags=json.dumps(sorted(r.seed.tags)),
                    )
                    .returning(cases.c.id)
                ).scalar_one()
                rows = [
                    _output_row(case_id, "source", i, o) for i, o in enumerate(r.source_outputs)
                ]
                rows.append(_output_row(case_id, "followup", 0, r.followup_output))
                conn.execute(insert(outputs), rows)
                v = r.verdict
                conn.execute(
                    insert(verdicts).values(
                        case_id=case_id,
                        status=v.status.value,
                        mode=r.relation.mode.value,
                        comparator_result_json=json.dumps(
                            {
                                "score": v.score,
                                "threshold": v.threshold,
                                "detail": v.detail,
                                "scores": [c.score for c in v.comparisons],
                            }
                        ),
                        is_violation=v.is_violation,
                        self_variance=v.self_variance,
                    )
                )

    def finish_run(
        self, run_id: str, status: str, cost_usd: float, summary: dict[str, Any]
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    finished_at=datetime.now(UTC),
                    status=status,
                    total_cost_usd=cost_usd,
                    summary_json=json.dumps(summary),
                )
            )

    def latest_run_id(self) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(
                select(runs.c.id).order_by(runs.c.started_at.desc()).limit(1)
            ).scalar()

    def load_report(self, run_id: str) -> RunReport | None:
        with self.engine.connect() as conn:
            run = conn.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
            if run is None:
                return None
            case_rows = (
                conn.execute(
                    select(cases, verdicts)
                    .join(verdicts, verdicts.c.case_id == cases.c.id)
                    .where(cases.c.run_id == run_id)
                    .order_by(cases.c.id)
                )
                .mappings()
                .all()
            )
            output_rows = (
                conn.execute(
                    select(outputs)
                    .join(cases, cases.c.id == outputs.c.case_id)
                    .where(cases.c.run_id == run_id)
                    .order_by(outputs.c.case_id, outputs.c.role, outputs.c.sample_idx)
                )
                .mappings()
                .all()
            )

        by_case: dict[int, dict[str, list[OutputView]]] = defaultdict(lambda: defaultdict(list))
        for o in output_rows:
            by_case[o["case_id"]][o["role"]].append(
                OutputView(
                    sample_idx=o["sample_idx"],
                    text=o["text"],
                    latency_ms=o["latency_ms"],
                    cost_usd=o["cost_usd"],
                    cached=o["cached"],
                    error=o["error"],
                )
            )

        case_views = []
        for c in case_rows:
            result = json.loads(c["comparator_result_json"])
            case_views.append(
                CaseView(
                    id=c["id"],
                    relation_id=c["relation_id"],
                    seed_id=c["seed_id"],
                    variant=c["variant"],
                    mode=c["mode"],
                    status=c["status"],
                    score=result["score"],
                    threshold=result["threshold"],
                    self_variance=c["self_variance"],
                    detail=result["detail"],
                    followup_note=c["followup_note"],
                    source_input=json.loads(c["source_input_json"]),
                    followup_input=json.loads(c["followup_input_json"]),
                    source_outputs=by_case[c["id"]]["source"],
                    followup_output=by_case[c["id"]]["followup"][0],
                    triage=c["triage"],
                )
            )

        summary = json.loads(run["summary_json"] or "{}")
        return RunReport(
            run=RunView(
                id=run["id"],
                started_at=run["started_at"],
                finished_at=run["finished_at"],
                git_sha=run["git_sha"],
                status=run["status"],
                total_cost_usd=run["total_cost_usd"],
                stats=summary.get("stats", {}),
            ),
            gate=GateResult.model_validate(summary["gate"]) if "gate" in summary else None,
            relations=summarize(case_views, summary.get("relations", {})),
            cases=case_views,
            skipped=[SkipView.model_validate(s) for s in summary.get("skipped", [])],
        )


def summarize(case_views: list[CaseView], modes: dict[str, str]) -> list[RelationSummary]:
    """Per-relation counts. `modes` lists every relation in the run, even those with no cases."""
    summaries = {rid: RelationSummary(id=rid, mode=Mode(mode)) for rid, mode in modes.items()}
    for c in case_views:
        s = summaries.setdefault(c.relation_id, RelationSummary(id=c.relation_id, mode=c.mode))
        s.cases += 1
        match c.status:
            case Status.PASS:
                s.passed += 1
            case Status.VIOLATION:
                s.violations += 1
            case Status.INCONCLUSIVE:
                s.inconclusive += 1
            case Status.ERROR:
                s.errors += 1
    return list(summaries.values())
