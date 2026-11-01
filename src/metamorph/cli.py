"""Command-line interface.

Exit codes: 0 pass, 1 blocking violations over the gate threshold, 2 config or runtime error.
"""

from __future__ import annotations

import asyncio
import functools
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
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Ignore cached responses.")] = False,
) -> None:
    """Generate follow-ups, call the target, check relations and write reports."""
    cfg = load_config(config)
    options = RunOptions(
        relations=[r.strip() for r in relations.split(",")] if relations else None,
        limit=limit,
        use_cache=not no_cache,
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
    """Render a stored run as JSON or JUnit XML."""
    store = open_store(load_config(config))
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
