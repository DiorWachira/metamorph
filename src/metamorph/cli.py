"""Command-line interface.

Exit codes: 0 pass, 1 blocking violations over the gate threshold, 2 config or runtime error.
"""

from __future__ import annotations

import asyncio
import functools
import io
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress
from rich.table import Table

from metamorph import templates
from metamorph.config import DEFAULT_CONFIG_NAME, load_config
from metamorph.errors import MetamorphError
from metamorph.relations import builtin_specs
from metamorph.reports import RENDERERS, ReportFormat, RunReport
from metamorph.runner.budget import Budget
from metamorph.suite import RunOptions, open_store, run_suite
from metamorph.types import Mode, Status

EXIT_PASS, EXIT_GATE_FAILED, EXIT_ERROR = 0, 1, 2

app = typer.Typer(
    help="Metamorphic testing and CI gating for LLM applications.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
relations_app = typer.Typer(help="Inspect the relation catalogue.", no_args_is_help=True)
app.add_typer(relations_app, name="relations")

for _stream in (sys.stdout, sys.stderr):
    # Windows pipes default to cp1252; reports carry emoji, Kiswahili and user text.
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

console = Console()
err = Console(stderr=True)

ConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Path to metamorph.yaml.", dir_okay=False)
]


def exits_on_error[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Map failures to exit code 2, keeping exit code 1 for gate failures only."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except MetamorphError as exc:
            err.print(f"[bold red]error:[/] {escape(str(exc))}")
            raise typer.Exit(EXIT_ERROR) from exc
        except (typer.Exit, KeyboardInterrupt):
            raise
        except Exception as exc:  # an unexpected crash must not look like a gate failure (1)
            err.print_exception()
            raise typer.Exit(EXIT_ERROR) from exc

    return wrapper


@app.command()
def init(
    directory: Annotated[Path, typer.Argument(help="Where to create the files.")] = Path("."),
    force: Annotated[bool, typer.Option(help="Overwrite existing files.")] = False,
) -> None:
    """Create a starter metamorph.yaml, seed file and placeholder target."""
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        DEFAULT_CONFIG_NAME: templates.CONFIG,
        "seeds.jsonl": templates.SEEDS,
        "app.py": templates.APP,
    }
    for name, content in files.items():
        path = directory / name
        if path.exists() and not force:
            console.print(f"[yellow]skip[/]  {path} (exists; use --force to overwrite)")
            continue
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]wrote[/] {path}")

    gitignore = directory / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".metamorph/" not in existing.splitlines():
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        gitignore.write_text(f"{existing}{prefix}.metamorph/\n", encoding="utf-8")
    console.print("\nNext: [bold]metamorph run[/]")


@app.command()
@exits_on_error
def run(
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
    relations: Annotated[
        str | None, typer.Option(help="Comma-separated relation ids to run (default: all enabled).")
    ] = None,
    limit: Annotated[int | None, typer.Option(min=1, help="Use only the first N seeds.")] = None,
    gate: Annotated[bool, typer.Option("--gate", help="Exit 1 if the gate fails.")] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Re-call the target (LLM follow-ups stay cached).")
    ] = False,
    budget_usd: Annotated[
        float | None, typer.Option(min=0.0, help="Stop starting paid calls beyond this spend.")
    ] = None,
) -> None:
    """Generate follow-ups, call the target, check relations and write reports."""
    cfg = load_config(config)
    options = RunOptions(
        relations=[r.strip() for r in relations.split(",")] if relations else None,
        limit=limit,
        use_cache=not no_cache,
        budget_usd=budget_usd,
    )

    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("calling target", total=None)
        report = asyncio.run(
            run_suite(
                cfg,
                options,
                on_total_calls=lambda n: progress.update(task, total=n),
                on_call_done=lambda: progress.advance(task),
            )
        )

    out_dir = cfg.resolve(cfg.storage_dir) / "reports" / report.run.id
    out_dir.mkdir(parents=True, exist_ok=True)
    for render, filename in RENDERERS.values():
        (out_dir / filename).write_text(render(report), encoding="utf-8")

    _print_summary(report)
    console.print(f"\nReports: {out_dir}")
    raise typer.Exit(_exit_code(report) if gate else EXIT_PASS)


@app.command()
@exits_on_error
def report(
    run_id: Annotated[str, typer.Argument(help="Run id, or 'latest'.")] = "latest",
    format: Annotated[ReportFormat, typer.Option("--format", "-f")] = "json",
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write to a file.")] = None,
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
) -> None:
    """Render a stored run as JSON, JUnit XML or HTML."""
    with open_store(load_config(config)) as store:
        resolved = store.latest_run_id() if run_id == "latest" else run_id
        loaded = store.load_report(resolved) if resolved else None
    if loaded is None:
        raise MetamorphError(f"no run found with id {run_id!r}")
    rendered = RENDERERS[format][0](loaded)
    if out:
        out.write_text(rendered, encoding="utf-8")
        console.print(f"wrote {out}")
    else:
        typer.echo(rendered, nl=False)


@relations_app.command("list")
@exits_on_error
def relations_list(config: ConfigOption = Path(DEFAULT_CONFIG_NAME)) -> None:
    """Show the built-in relations, marking those enabled in the config."""
    enabled: set[str] = set()
    if config.exists():
        cfg = load_config(config)
        enabled = {e if isinstance(e, str) else str(e.get("id")) for e in cfg.relations}
    table = Table()
    table.add_column("id", no_wrap=True)
    for header in ("on", "tags", "transform -> comparator", "description"):
        table.add_column(header)
    for rel_id, spec in builtin_specs().items():
        table.add_row(
            rel_id,
            "yes" if rel_id in enabled else "",
            ", ".join(spec.get("tags", [])) or "any",
            f"{spec['transform']['name']} -> {spec['comparator']['name']}",
            spec["description"],
        )
    console.print(table)


def _exit_code(report: RunReport) -> int:
    gate = report.gate
    if gate is None or gate.too_many_errors:
        return EXIT_ERROR
    return EXIT_PASS if gate.passed else EXIT_GATE_FAILED


def _print_summary(report: RunReport) -> None:
    stats: dict[str, Any] = report.run.stats
    console.print(
        f"[bold]Run {report.run.id}[/]  "
        f"calls: {stats.get('requested', 0)} requested, {stats.get('cache_hits', 0)} cached, "
        f"{stats.get('errors', 0)} failed  cost: ${report.run.total_cost_usd:.4f}"
    )
    if llm := report.run.llm:
        console.print(
            f"helper model {escape(str(llm['model']))}: {llm['calls']} calls, "
            f"{llm['cache_hits']} cached, {llm['failures']} failed"
        )
    table = Table("relation", "mode", "cases", "pass", "violations", "inconclusive", "errors")
    for r in report.relations:
        mode = "[bold]BLOCKING[/]" if r.mode is Mode.BLOCKING else "warning"
        violations = f"[red]{r.violations}[/]" if r.violations else "0"
        table.add_row(
            r.id, mode, str(r.cases), str(r.passed), violations, str(r.inconclusive), str(r.errors)
        )
    console.print(table)

    for case in report.violations[:10]:
        colour = "red" if case.mode is Mode.BLOCKING else "yellow"
        console.print(
            f"[{colour}]x {case.relation_id}[/] seed={escape(case.seed_id)}: {escape(case.detail)}"
        )
        console.print(f"    {case.followup_note}", markup=False)
    if len(report.violations) > 10:
        console.print(f"  ...and {len(report.violations) - 10} more (see the JSON report)")

    effect = report.baseline_effect
    if report.run.samples > 1:
        console.print(
            f"self-variance baseline (k={report.run.samples}): {effect['excused']} of "
            f"{effect['naive_violations']} disagreements were the target's own noise; "
            f"{len({u.seed_id for u in report.unstable_inputs})} inputs unstable on their own"
        )
    if report.run.status == "budget_exhausted":
        console.print("[yellow]budget exhausted: the run stopped early; unrun cases are skipped[/]")
    if report.skipped:
        console.print(f"[dim]{len(report.skipped)} relation/seed pairs skipped (see report)[/]")
    errors = [c for c in report.cases if c.status is Status.ERROR]
    if errors:
        console.print(f"[red]{len(errors)} cases errored[/], e.g. {escape(errors[0].detail)}")

    gate = report.gate
    if gate is not None:
        verdict = "[green]PASSED[/]" if gate.passed else "[red]FAILED[/]"
        reasons = f": {escape('; '.join(gate.reasons))}" if gate.reasons else ""
        console.print(f"Gate {verdict}{reasons}")


@relations_app.command("stats")
@exits_on_error
def relations_stats(
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
    export: Annotated[
        bool, typer.Option("--export", help="Write relations/learned.yaml for CI.")
    ] = False,
) -> None:
    """Show triage precision per relation and the mode it has earned."""
    from metamorph.collection import save_learned
    from metamorph.promotion import MIN_PRECISION, MIN_REVIEWED

    cfg = load_config(config)
    with open_store(cfg) as store:
        stats = store.relation_stats()
    if export:
        path = cfg.resolve(cfg.learned_modes)
        save_learned(path, stats)
        console.print(f"wrote {path}: commit it so CI applies the learned modes")
    if not stats:
        console.print("No triaged violations yet. Run `metamorph triage` to review some.")
        return
    table = Table("relation", "reviewed", "true bugs", "false alarms", "precision", "learned mode")
    for s in stats:
        precision = "n/a" if s.precision is None else f"{s.precision:.0%}"
        learned = s.learned_mode.value if s.learned_mode else f"(needs {MIN_REVIEWED})"
        table.add_row(
            s.relation_id,
            str(s.reviewed),
            str(s.true_bugs),
            str(s.false_alarms),
            precision,
            learned,
        )
    console.print(table)
    console.print(
        f"[dim]A relation blocks CI after {MIN_REVIEWED} reviews at >= {MIN_PRECISION:.0%} "
        "precision, unless metamorph.yaml pins its mode.[/]"
    )


@app.command()
@exits_on_error
def serve(
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
    host: Annotated[str, typer.Option(help="Interface to bind (local only by default).")] = (
        "127.0.0.1"
    ),
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = False,
    path: Annotated[str, typer.Option(hidden=True)] = "/",
) -> None:
    """Start the triage UI and API."""
    try:
        import uvicorn

        from metamorph.server.app import create_app
    except ImportError as exc:
        raise MetamorphError('the UI needs: pip install "metamorph[server]"') from exc

    url = f"http://{host}:{port}{path}"
    console.print(f"Metamorph cabinet at [bold]{url}[/]  (Ctrl+C to stop)")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    uvicorn.run(create_app(load_config(config)), host=host, port=port, log_level="warning")


@app.command()
@exits_on_error
def triage(
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8765,
) -> None:
    """Open the latest run's violations in the triage UI."""
    serve(config=config, port=port, open_browser=True, path="/runs/latest")


@relations_app.command("proposals")
@exits_on_error
def relations_proposals(config: ConfigOption = Path(DEFAULT_CONFIG_NAME)) -> None:
    """List relations proposed by the miner and awaiting a decision."""
    from metamorph.collection import load_proposals, proposals_path

    proposals = load_proposals(proposals_path(load_config(config)))
    pending = [p for p in proposals if p.status == "proposed"]
    if not pending:
        console.print("No pending proposals. Run `metamorph mine SPEC.md` to propose some.")
        return
    for p in pending:
        spec = p.spec
        console.print(
            f"[bold]{escape(spec.id)}[/]  {spec.transform.name} -> {spec.comparator.name}"
            f" ({spec.expected.value})"
        )
        console.print(f"  {escape(spec.description)}")
        if spec.requirement:
            console.print(f'  [dim]requirement: "{escape(spec.requirement)}"[/]')
        if p.rationale:
            console.print(f"  [dim]bug it targets: {escape(p.rationale)}[/]")
    console.print()
    console.print("Approve with `metamorph relations approve ID...` (or reject).")


def _decide(config: Path, ids: list[str], every: bool, status: str) -> None:
    from metamorph.collection import decide, load_proposals, proposals_path

    cfg = load_config(config)
    if every:
        ids = [p.spec.id for p in load_proposals(proposals_path(cfg)) if p.status == "proposed"]
    if not ids:
        raise MetamorphError("name at least one proposal id (or pass --all)")
    decided = decide(cfg, ids, status)  # type: ignore[arg-type]
    where = cfg.resolve(cfg.custom_relations) if status == "approved" else "proposed.yaml"
    console.print(f"{status} {len(decided)}: {', '.join(decided)} -> {where}")


@relations_app.command("approve")
@exits_on_error
def relations_approve(
    ids: Annotated[list[str] | None, typer.Argument(help="Proposal ids.")] = None,
    every: Annotated[bool, typer.Option("--all", help="Approve every pending proposal.")] = False,
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
) -> None:
    """Approve proposals into relations/custom.yaml (enabled on the next run)."""
    _decide(config, ids or [], every, "approved")


@relations_app.command("reject")
@exits_on_error
def relations_reject(
    ids: Annotated[list[str] | None, typer.Argument(help="Proposal ids.")] = None,
    every: Annotated[bool, typer.Option("--all", help="Reject every pending proposal.")] = False,
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
) -> None:
    """Reject proposals (kept on file so they are not proposed again)."""
    _decide(config, ids or [], every, "rejected")


@app.command()
@exits_on_error
def mine(
    spec: Annotated[Path, typer.Argument(help="Requirements, SPEC or system prompt file.")],
    config: ConfigOption = Path(DEFAULT_CONFIG_NAME),
    limit: Annotated[int, typer.Option(min=1, max=20, help="Most proposals to ask for.")] = 8,
    hint: Annotated[str, typer.Option(help="One line about what the app does.")] = "",
) -> None:
    """Propose app-specific relations from requirements, for human approval."""
    from metamorph.collection import load_custom, load_proposals, proposals_path, save_proposals
    from metamorph.miner import mine as run_miner
    from metamorph.relations import builtin_specs
    from metamorph.runner.cache import Cache
    from metamorph.suite import build_llm

    cfg = load_config(config)
    if cfg.llm is None:
        raise MetamorphError("mining needs a helper model: add an `llm:` section to metamorph.yaml")
    if not spec.exists():
        raise MetamorphError(f"requirements file not found: {spec}")
    path = proposals_path(cfg)
    existing = load_proposals(path)
    taken = set(builtin_specs()) | {s.id for s in load_custom(cfg.resolve(cfg.custom_relations))}
    taken |= {p.spec.id for p in existing}

    async def go() -> tuple[Any, str]:
        cache = Cache(cfg.resolve(cfg.storage_dir) / "cache.sqlite")
        llm = build_llm(cfg, cache, Budget(cfg.run.budget_usd), None)
        assert llm is not None
        try:
            result = await run_miner(
                llm, spec.read_text(encoding="utf-8"), spec.name, taken, hint, limit
            )
        finally:
            await llm.aclose()
            cache.close()
        return result, f"${llm.stats.cost_usd:.4f}"

    with console.status("mining relations from the requirements..."):
        result, cost = asyncio.run(go())
    save_proposals(path, existing + result.proposals)
    console.print(f"{len(result.proposals)} proposals written to {path} (cost {cost})")
    for rel_id, reason in result.rejected:
        console.print(f"[yellow]dropped[/] {escape(rel_id)}: {escape(reason)}")
    if result.proposals:
        console.print("Review them with `metamorph relations proposals` or in the cabinet UI.")
