"""Result tables (SQLAlchemy Core). Only portable types are used, so a Postgres URL works too."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

runs = Table(
    "runs",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("git_sha", String(64)),
    Column("config_json", Text, nullable=False),
    Column("total_cost_usd", Float, nullable=False, default=0.0),
    Column("status", String(20), nullable=False),  # running | completed | error
    Column("summary_json", Text),  # call stats, gate result, skipped cases
)

cases = Table(
    "cases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "run_id", String(40), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    ),
    Column("relation_id", String(100), nullable=False, index=True),
    Column("seed_id", String(200), nullable=False),
    Column("variant", Integer, nullable=False, default=0),
    Column("source_input_json", Text, nullable=False),
    Column("followup_input_json", Text, nullable=False),
    Column("followup_note", Text, nullable=False, default=""),
    Column("tags", Text, nullable=False, default="[]"),
)

outputs = Table(
    "outputs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "case_id", Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    ),
    Column("role", String(10), nullable=False),  # source | followup
    Column("sample_idx", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("tokens_in", Integer),
    Column("tokens_out", Integer),
    Column("cost_usd", Float, nullable=False, default=0.0),
    Column("cached", Boolean, nullable=False, default=False),
    Column("error", Text),
)

verdicts = Table(
    "verdicts",
    metadata,
    Column("case_id", Integer, ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
    Column("status", String(20), nullable=False),  # pass | violation | inconclusive | error
    Column("mode", String(10), nullable=False),  # relation mode at run time
    Column("comparator_result_json", Text, nullable=False),
    Column("is_violation", Boolean, nullable=False),
    Column("self_variance", Float),
    Column("triage", String(20), nullable=False, default="unreviewed"),
    Column("note", Text),
    Column("triaged_at", DateTime(timezone=True)),
)

relation_stats = Table(
    "relation_stats",
    metadata,
    Column("relation_id", String(100), primary_key=True),
    Column("reviewed", Integer, nullable=False, default=0),
    Column("true_bugs", Integer, nullable=False, default=0),
    Column("false_alarms", Integer, nullable=False, default=0),
    Column("precision", Float),
    Column("mode", String(10)),  # learned mode; NULL until enough violations are triaged
    Column("updated_at", DateTime(timezone=True)),
)
