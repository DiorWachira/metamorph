"""Run a whole suite: resolve config, call the target, judge, persist, gate."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

from metamorph.adapters import Target, build_target
from metamorph.config import Config
from metamorph.gate import evaluate_gate
from metamorph.gitinfo import git_info
from metamorph.relations import resolve_relations
from metamorph.reports.model import RunReport
from metamorph.runner.cache import ResponseCache
from metamorph.runner.engine import execute, plan
from metamorph.runner.executor import CallExecutor
from metamorph.seeds import load_seeds
from metamorph.storage import Store, sqlite_url
from metamorph.transforms import Resources


@dataclass(frozen=True)
class RunOptions:
    relations: list[str] | None = None
    limit: int | None = None
    use_cache: bool = True


def new_run_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def open_store(config: Config) -> Store:
    return Store(sqlite_url(config.resolve(config.storage_dir)))


async def run_suite(
    config: Config,
    options: RunOptions | None = None,
    target: Target | None = None,
    on_total_calls: Callable[[int], None] | None = None,
    on_call_done: Callable[[], None] | None = None,
) -> RunReport:
    """Execute one run end to end and return its report. `target` overrides config (tests)."""
    options = options or RunOptions()
    relations = resolve_relations(config, options.relations)
    seeds = load_seeds(config.resolve(config.seeds), options.limit)
    res = config.resources
    resources = Resources.load(
        config.resolve(res.distractors) if res.distractors else None,
        config.resolve(res.entity_bank) if res.entity_bank else None,
    )
    planned, skipped = plan(relations, seeds, config.run, config.fields, resources)

    storage_dir = config.resolve(config.storage_dir)
    store = open_store(config)
    git = git_info(config.base_dir)
    run_id = new_run_id()
    store.create_run(run_id, git.sha, config.snapshot)

    target = target or build_target(config.target, config.base_dir)
    cache = (
        ResponseCache(storage_dir / "cache.sqlite")
        if config.cache.enabled and options.use_cache
        else None
    )
    namespace = target.fingerprint
    if config.cache.invalidate_on_code_change:
        namespace += git.code_fingerprint
    executor = CallExecutor(
        target,
        cache,
        namespace,
        concurrency=config.run.concurrency,
        retries=config.run.retries,
        backoff_s=config.run.backoff_s,
        on_done=on_call_done,
    )
    try:
        results = await execute(planned, executor, config.run, on_total_calls)
    except Exception as exc:
        store.finish_run(run_id, "error", executor.stats.cost_usd, {"error": str(exc)})
        raise
    finally:
        await target.aclose()
        if cache:
            cache.close()

    gate = evaluate_gate(results, config.gate)
    store.save_results(run_id, results)
    store.finish_run(
        run_id,
        "completed",
        executor.stats.cost_usd,
        {
            "stats": asdict(executor.stats),
            "gate": gate.model_dump(),
            "relations": {r.id: r.mode.value for r in relations},
            "skipped": [asdict(s) for s in skipped],
        },
    )
    report = store.load_report(run_id)
    assert report is not None
    return report
