"""Persistence for runs, cases and triage, and loading them back as report models."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection, Engine, RowMapping, create_engine, func, insert, select, update

from metamorph.errors import MetamorphError
from metamorph.promotion import learned_mode, precision
from metamorph.reports.model import (
    CaseView,
    GateResult,
    OutputView,
    RelationSummary,
    RunReport,
    RunView,
    SkipView,
    Triage,
)
from metamorph.runner.engine import CaseResult
from metamorph.storage.schema import cases, metadata, outputs, relation_stats, runs, verdicts
from metamorph.types import Mode, Status, TargetOutput
from metamorph.util import canonical_json


class RelationStats(BaseModel):
    relation_id: str
    reviewed: int
    true_bugs: int
    false_alarms: int
    precision: float | None
    learned_mode: Mode | None


class RunListItem(BaseModel):
    id: str
    started_at: datetime
    status: str
    git_sha: str | None
    total_cost_usd: float
    cases: int
    violations: int
    blocking_violations: int
    gate_passed: bool | None


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


def _case_view(row: RowMapping, by_role: dict[str, list[OutputView]]) -> CaseView:
    result = json.loads(row["comparator_result_json"])
    return CaseView(
        id=row["id"],
        run_id=row["run_id"],
        relation_id=row["relation_id"],
        seed_id=row["seed_id"],
        variant=row["variant"],
        mode=row["mode"],
        status=row["status"],
        score=result["score"],
        threshold=result["threshold"],
        nominal_threshold=result.get("nominal_threshold"),
        self_variance=row["self_variance"],
        detail=result["detail"],
        followup_note=row["followup_note"],
        source_input=json.loads(row["source_input_json"]),
        followup_input=json.loads(row["followup_input_json"]),
        source_outputs=by_role["source"],
        followup_output=by_role["followup"][0],
        triage=row["triage"],
        note=row["note"],
    )


class Store:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(url)
        metadata.create_all(self.engine)

    def close(self) -> None:
        """Release pooled connections (on Windows an open SQLite file cannot be deleted)."""
        self.engine.dispose()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- writing runs -----------------------------------------------------------------------

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
                                "nominal_threshold": v.nominal_threshold,
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

    # --- reading runs -----------------------------------------------------------------------

    def latest_run_id(self) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(
                select(runs.c.id).order_by(runs.c.started_at.desc()).limit(1)
            ).scalar()

    def list_runs(self, limit: int = 100) -> list[RunListItem]:
        violation = verdicts.c.status == Status.VIOLATION.value
        counts = (
            select(
                cases.c.run_id,
                func.count().label("cases"),
                func.count().filter(violation).label("violations"),
                func.count()
                .filter(violation, verdicts.c.mode == Mode.BLOCKING.value)
                .label("blocking"),
            )
            .join(verdicts, verdicts.c.case_id == cases.c.id)
            .group_by(cases.c.run_id)
            .subquery()
        )
        query = (
            select(runs, counts.c.cases, counts.c.violations, counts.c.blocking)
            .outerjoin(counts, counts.c.run_id == runs.c.id)
            .order_by(runs.c.started_at.desc())
            .limit(limit)
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        items = []
        for row in rows:
            gate = json.loads(row["summary_json"] or "{}").get("gate")
            items.append(
                RunListItem(
                    id=row["id"],
                    started_at=row["started_at"],
                    status=row["status"],
                    git_sha=row["git_sha"],
                    total_cost_usd=row["total_cost_usd"],
                    cases=row["cases"] or 0,
                    violations=row["violations"] or 0,
                    blocking_violations=row["blocking"] or 0,
                    gate_passed=gate["passed"] if gate else None,
                )
            )
        return items

    @staticmethod
    def _outputs_by_case(
        conn: Connection, case_ids: Sequence[int]
    ) -> dict[int, dict[str, list[OutputView]]]:
        by_case: dict[int, dict[str, list[OutputView]]] = defaultdict(lambda: defaultdict(list))
        rows = conn.execute(
            select(outputs)
            .where(outputs.c.case_id.in_(case_ids))
            .order_by(outputs.c.case_id, outputs.c.role, outputs.c.sample_idx)
        ).mappings()
        for o in rows:
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
        return by_case

    def load_case(self, case_id: int) -> CaseView | None:
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    select(cases, verdicts)
                    .join(verdicts, verdicts.c.case_id == cases.c.id)
                    .where(cases.c.id == case_id)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return _case_view(row, self._outputs_by_case(conn, [case_id])[case_id])

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
            by_case = self._outputs_by_case(conn, [c["id"] for c in case_rows])

        case_views = [_case_view(c, by_case[c["id"]]) for c in case_rows]
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
                llm=summary.get("llm"),
                budget=summary.get("budget"),
                samples=summary.get("samples", 1),
            ),
            gate=GateResult.model_validate(summary["gate"]) if "gate" in summary else None,
            relations=summarize(case_views, summary.get("relations", {})),
            cases=case_views,
            skipped=[SkipView.model_validate(s) for s in summary.get("skipped", [])],
        )

    # --- triage and learned modes -----------------------------------------------------------

    def triage(self, case_id: int, verdict: Triage, note: str | None = None) -> RelationStats:
        """Record a human verdict on a violation and update the relation's precision."""
        with self.engine.begin() as conn:
            row = conn.execute(
                select(cases.c.relation_id, verdicts.c.status)
                .join(verdicts, verdicts.c.case_id == cases.c.id)
                .where(cases.c.id == case_id)
            ).first()
            if row is None:
                raise MetamorphError(f"no case with id {case_id}")
            relation_id, status = row
            if status != Status.VIOLATION.value:
                raise MetamorphError("only violations can be triaged")
            conn.execute(
                update(verdicts)
                .where(verdicts.c.case_id == case_id)
                .values(
                    triage=verdict,
                    note=note,
                    triaged_at=datetime.now(UTC) if verdict != "unreviewed" else None,
                )
            )
            return self._refresh_stats(conn, relation_id)

    @staticmethod
    def _refresh_stats(conn: Connection, relation_id: str) -> RelationStats:
        counts: dict[str, int] = {
            triage: n
            for triage, n in conn.execute(
                select(verdicts.c.triage, func.count())
                .join(cases, cases.c.id == verdicts.c.case_id)
                .where(cases.c.relation_id == relation_id)
                .group_by(verdicts.c.triage)
            )
        }
        true_bugs, false_alarms = counts.get("true_bug", 0), counts.get("false_alarm", 0)
        stats = RelationStats(
            relation_id=relation_id,
            reviewed=true_bugs + false_alarms,
            true_bugs=true_bugs,
            false_alarms=false_alarms,
            precision=precision(true_bugs, false_alarms),
            learned_mode=learned_mode(true_bugs, false_alarms),
        )
        values = {
            "reviewed": stats.reviewed,
            "true_bugs": true_bugs,
            "false_alarms": false_alarms,
            "precision": stats.precision,
            "mode": stats.learned_mode.value if stats.learned_mode else None,
            "updated_at": datetime.now(UTC),
        }
        # Update-then-insert keeps this portable across SQLite and Postgres.
        done = conn.execute(
            update(relation_stats).where(relation_stats.c.relation_id == relation_id).values(values)
        )
        if done.rowcount == 0:
            conn.execute(insert(relation_stats).values(relation_id=relation_id, **values))
        return stats

    def relation_stats(self) -> list[RelationStats]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(relation_stats).order_by(relation_stats.c.relation_id)
            ).mappings()
            return [
                RelationStats(
                    relation_id=r["relation_id"],
                    reviewed=r["reviewed"],
                    true_bugs=r["true_bugs"],
                    false_alarms=r["false_alarms"],
                    precision=r["precision"],
                    learned_mode=r["mode"],
                )
                for r in rows
            ]

    def learned_modes(self) -> dict[str, Mode]:
        return {s.relation_id: s.learned_mode for s in self.relation_stats() if s.learned_mode}


def summarize(case_views: list[CaseView], relations: dict[str, Any]) -> list[RelationSummary]:
    """Per-relation counts. `relations` describes every relation in the run, even those with no
    cases; runs stored before M2 hold just the mode string."""
    summaries: dict[str, RelationSummary] = {}
    for rid, info in relations.items():
        fields = info if isinstance(info, dict) else {"mode": info}
        summaries[rid] = RelationSummary(id=rid, **fields)
    for c in case_views:
        s = summaries.setdefault(c.relation_id, RelationSummary(id=c.relation_id, mode=c.mode))
        s.cases += 1
        s.excused += c.excused_by_baseline
        match c.status:
            case Status.PASS:
                s.passed += 1
            case Status.VIOLATION:
                s.violations += 1
            case Status.INCONCLUSIVE:
                s.inconclusive += 1
            case Status.ERROR:
                s.errors += 1
            case Status.SKIPPED:
                s.skipped += 1
    return list(summaries.values())
