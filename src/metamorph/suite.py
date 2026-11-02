"""Run a whole suite: resolve config, plan follow-ups, call the target, judge, persist, gate."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from metamorph.adapters import Target, build_target
from metamorph.collection import load_learned
from metamorph.config import Config
from metamorph.gate import evaluate_gate
from metamorph.gitinfo import git_info
from metamorph.llm import LLMProvider, LLMService, build_provider
from metamorph.relations import Relation, resolve_relations
from metamorph.reports.model import RunReport
from metamorph.runner.budget import Budget
from metamorph.runner.cache import Cache
from metamorph.runner.engine import execute, plan
from metamorph.runner.executor import CallExecutor
from metamorph.runner.pacing import limiter
from metamorph.seeds import load_seeds
from metamorph.services import Services
from metamorph.storage import Store, sqlite_url
from metamorph.transforms import Resources
from metamorph.types import Mode


@dataclass(frozen=True)
class RunOptions:
    relations: list[str] | None = None
    limit: int | None = None
    use_cache: bool = True  # False re-calls the target; helper-LLM follow-ups stay cached
    budget_usd: float | None = None  # overrides run.budget_usd


def new_run_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def open_store(config: Config) -> Store:
    return Store(sqlite_url(config.resolve(config.storage_dir)))


def learned_modes(config: Config, store: Store) -> dict[str, Mode]:
    """Modes earned through triage: the committed file (what CI sees) over the local store."""
    return {**store.learned_modes(), **load_learned(config.resolve(config.learned_modes))}


def relation_summary(relation: Relation) -> dict[str, Any]:
    spec = relation.spec
    return {
        "mode": relation.mode.value,
        "mode_source": relation.mode_source,
        "description": spec.description,
        "transform": spec.transform.name,
        "comparator": spec.comparator.name,
        "threshold": relation.threshold,
        "expected": spec.expected.value,
    }


def build_llm(
    config: Config, cache: Cache | None, budget: Budget, provider: LLMProvider | None
) -> LLMService | None:
    if config.llm is None and provider is None:
        return None
    llm_cfg = config.llm
    if provider is None:
        assert llm_cfg is not None
        provider = build_provider(llm_cfg, config.base_dir)
    record_to = config.resolve(llm_cfg.record_to) if llm_cfg and llm_cfg.record_to else None
    concurrency = llm_cfg.concurrency if llm_cfg else 4
    pace = limiter(llm_cfg.requests_per_minute) if llm_cfg else None
    return LLMService(provider, cache, budget, concurrency, record_to, pace)


async def run_suite(
    config: Config,
    options: RunOptions | None = None,
    target: Target | None = None,
    llm_provider: LLMProvider | None = None,
    on_total_calls: Callable[[int], None] | None = None,
    on_call_done: Callable[[], None] | None = None,
) -> RunReport:
    """Execute one run end to end and return its report.

    `target` and `llm_provider` override the config; tests use them to inject fakes.
    """
    options = options or RunOptions()
    with open_store(config) as store:
        return await _run(
            config, options, store, target, llm_provider, on_total_calls, on_call_done
        )


async def _run(
    config: Config,
    options: RunOptions,
    store: Store,
    target: Target | None,
    llm_provider: LLMProvider | None,
    on_total_calls: Callable[[int], None] | None,
    on_call_done: Callable[[], None] | None,
) -> RunReport:
    relations = resolve_relations(config, options.relations, learned_modes(config, store))
    seeds = load_seeds(config.resolve(config.seeds), options.limit)
    res = config.resources
    resources = Resources.load(
        config.resolve(res.distractors) if res.distractors else None,
        config.resolve(res.entity_bank) if res.entity_bank else None,
    )

    storage_dir = config.resolve(config.storage_dir)
    cache = Cache(storage_dir / "cache.sqlite") if config.cache.enabled else None
    budget = Budget(options.budget_usd or config.run.budget_usd)
    llm = build_llm(config, cache, budget, llm_provider)
    services = Services(llm=llm)
    for relation in relations:
        relation.bind(services)

    git = git_info(config.base_dir)
    run_id = new_run_id()
    store.create_run(run_id, git.sha, config.snapshot)

    target = target or build_target(config.target, config.base_dir)
    namespace = target.fingerprint
    if config.cache.invalidate_on_code_change:
        namespace += git.code_fingerprint
    executor = CallExecutor(
        target,
        cache if options.use_cache else None,
        namespace,
        concurrency=config.run.concurrency,
        retries=config.run.retries,
        backoff_s=config.run.backoff_s,
        on_done=on_call_done,
        budget=budget,
        pace=limiter(config.run.requests_per_minute),
    )

    def total_cost() -> float:
        return executor.stats.cost_usd + (llm.stats.cost_usd if llm else 0.0)

    try:
        planned, skipped = await plan(relations, seeds, config.run, config.fields, resources)
        results = await execute(planned, executor, config.run, on_total_calls)
    except Exception as exc:
        store.finish_run(run_id, "error", total_cost(), {"error": str(exc)})
        raise
    finally:
        await target.aclose()
        if llm:
            await llm.aclose()
        if cache:
            cache.close()

    gate = evaluate_gate(results, config.gate)
    store.save_results(run_id, results)
    store.finish_run(
        run_id,
        "budget_exhausted" if budget.tripped else "completed",
        total_cost(),
        {
            "stats": asdict(executor.stats),
            "llm": {"model": llm.model, **asdict(llm.stats)} if llm else None,
            "budget": {"limit_usd": budget.limit_usd, "spent_usd": budget.spent_usd},
            "samples": config.run.samples,
            "gate": gate.model_dump(),
            "relations": {r.id: relation_summary(r) for r in relations},
            "skipped": [asdict(s) for s in skipped],
        },
    )
    report = store.load_report(run_id)
    assert report is not None
    return report
