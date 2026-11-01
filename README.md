# Metamorph

**Test an LLM application without a single labelled answer, and gate CI on the result.**

[![CI](https://github.com/DiorWachira/metamorph/actions/workflows/ci.yml/badge.svg)](https://github.com/DiorWachira/metamorph/actions/workflows/ci.yml)

LLM apps are hard to test because there is no oracle: for most inputs nobody has written down
the correct output. *Metamorphic testing* sidesteps that. You may not know the right answer to
a question, but you do know that reordering the retrieved documents, adding an irrelevant
paragraph or making a typo should not change it. Metamorph generates those follow-up inputs,
calls your app as a black box, checks the *relation* between the outputs, and exits non-zero in
CI when a blocking relation is violated.

What sets it apart:

- **App-level and CI-native.** It tests your deployed endpoint or Python function, not a raw
  model, and gates pull requests with exit codes.
- **It attacks false alarms.** A self-variance baseline means a follow-up fails only if it
  disagrees with the source more than the app disagrees with itself. Per-relation precision,
  learned from triage, comes in M3.
- **Relations for Kenyan products**: English, Swahili and Sheng code-switch invariance (M2).

> **Status:** milestone 1 of 5 (core engine) is done. See the [roadmap](#roadmap).

## 60-second quickstart

```bash
git clone https://github.com/DiorWachira/metamorph && cd metamorph
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[examples]"

cd examples/rag_kenya
metamorph run --gate          # exits 1: the planted bug is caught
RAG_FIXED=1 metamorph run --gate --no-cache    # exits 0 (PowerShell: $env:RAG_FIXED=1)
```

```
Run 20261101-163029-633b  calls: 63 requested, 0 cached, 0 failed  cost: $0.0000
| relation                 | mode     | cases | pass | violations | inconclusive | errors |
| doc-order-invariance     | BLOCKING | 15    | 2    | 13         | 0            | 0      |
| distractor-invariance    | warning  | 15    | 12   | 3          | 0            | 0      |
| typo-robustness          | warning  | 15    | 15   | 0          | 0            | 0      |
| number-format-invariance | warning  | 1     | 1    | 0          | 0            | 0      |
| entity-swap-invariance   | warning  | 2     | 2    | 0          | 0            | 0      |
x doc-order-invariance seed=constitution-date: token F1 0.17
    documents reordered to [2, 0, 1]
...
Gate FAILED: 13 blocking violations > allowed 0
```

The demo is a small RAG app over public facts about Kenya. Its generator reads only the
**first** retrieved chunk. Every example-based test passes, because retrieval usually ranks the
right chunk first. Shuffling the same chunks changes the answer, and `doc-order-invariance`
catches the bug without anyone labelling a single answer. Run it again and all 63 calls come
from the cache at zero cost, with identical verdicts.

To start on your own app:

```bash
metamorph init           # writes metamorph.yaml, seeds.jsonl and a placeholder app.py
metamorph run --gate
```

## How it works

```mermaid
flowchart LR
    S[seeds.jsonl] --> P
    C[metamorph.yaml] --> P
    subgraph Engine
        P[Planner<br/>transform each seed<br/>seeded RNG] --> X[Executor<br/>asyncio + retries<br/>concurrency limit]
        X <--> K[(Response cache<br/>SQLite)]
        X <--> T[Target adapter<br/>python / http]
        X --> J[Judge<br/>comparator score vs<br/>self-variance baseline]
    end
    T <--> A[Your LLM app]
    J --> DB[(Results DB<br/>SQLite / Postgres)]
    DB --> R[Reports<br/>JSON / JUnit]
    J --> G{Gate}
    G -->|0 pass / 1 fail / 2 error| CI[CI exit code]
```

1. **Plan.** For every seed and every applicable relation, the transform produces a follow-up
   input. Each transform's RNG is seeded from `(run seed, relation, seed, variant)`, so a
   re-run reproduces identical follow-ups and every call hits the cache.
2. **Call.** Unique `(input, sample)` pairs are collected first. Source outputs are shared
   across relations, so each source is called only once. The calls then run concurrently,
   with retries and exponential backoff on timeouts, 429 and 5xx.
3. **Judge.** A comparator scores agreement between the source and follow-up outputs from 0 to
   1. An invariance relation is violated when:

   ```
   best_score  <  min(threshold, self_agreement − margin)
   ```

   where `self_agreement` is the lowest agreement among `k` samples of the *same* source input
   (`run.samples`). A stable app is held to the threshold. An app that is noisy on its own is
   not blamed for that noise. With `samples: 1` the threshold applies on its own.
4. **Gate.** Only **blocking** violations count. A high target error rate is reported as a
   runtime error (exit 2), not as a pass.

### Exit codes

| code | meaning |
|---|---|
| 0 | gate passed (or `--gate` not given) |
| 1 | blocking violations exceed `gate.max_blocking_violations` / `max_blocking_rate` |
| 2 | config error, runtime crash, or target error rate above `gate.max_error_rate` |

## Configuration

```yaml
target:
  type: http                       # or: python (callable: "module:function")
  url: http://127.0.0.1:8000/answer
  output_path: $.answer            # JSONPath to the answer; omit to use the whole body
  headers: {Authorization: "Bearer ${APP_TOKEN}"}   # ${VAR} comes from the environment

seeds: seeds.jsonl                 # {"id": "...", "tags": ["rag"], "input": {...}} per line

fields:                            # where transforms find things in your input (dotted paths)
  text: question
  documents: documents             # list of strings or objects ({text: ...}); for RAG relations

relations:
  - typo-robustness                # built-in, default settings (WARNING)
  - id: doc-order-invariance       # built-in with overrides
    mode: blocking
    comparator: {name: token_f1, threshold: 0.9}
  - id: totals-stable              # fully custom
    description: Reformatting numbers must not change the computed total.
    transform: {name: number_format}
    comparator: {name: numeric_within, params: {path: "$.total", tol: 0.01}}

run:
  seed: 0            # reproducible follow-ups
  samples: 1         # k source samples for the self-variance baseline
  margin: 0.05
  concurrency: 8
  retries: 3

gate:
  max_blocking_violations: 0
  max_error_rate: 0.1

cache:
  enabled: true
  invalidate_on_code_change: true  # cache keys include git HEAD + working-tree diff
```

Secrets are expanded from the environment at load time. Run snapshots in the database store
the config *as written*, so expanded secrets are never saved.

**RAG apps** need a way to accept context in the request (here, `documents`), so that
Metamorph can reorder it or add a distractor. The demo's `/answer` endpoint retrieves when
`documents` is absent and uses the given context when it is present.

## Relation catalogue

| id | transform | comparator | checks that… |
|---|---|---|---|
| `doc-order-invariance` | `shuffle_documents` | `token_f1 ≥ 0.8` | reordering retrieved docs keeps the answer (RAG) |
| `distractor-invariance` | `inject_distractor` | `token_f1 ≥ 0.8` | an irrelevant paragraph does not change the answer |
| `typo-robustness` | `typos` (rate 0.1) | `token_f1 ≥ 0.8` | keyboard typos in the question do not change the answer |
| `number-format-invariance` | `number_format` | `token_f1 ≥ 0.8` | `1000` ↔ `1,000` does not change the answer |
| `entity-swap-invariance` | `swap_entities` | `token_f1 ≥ 0.8` | swapping irrelevant names (mapped back before comparing) keeps the answer |
| `json-schema-stability` | `surface_noise` | `json_schema_equal` | formatting noise keeps a JSON output's keys and types |

Coming in M2: `paraphrase-invariance`, `translation-roundtrip-sw`, `code-switch-invariance`
(English, Swahili and Sheng), `politeness-invariance`, `negation-flip`, `refusal-consistency`.

**Transforms:** `shuffle_documents`, `inject_distractor(position)`, `typos(rate)`,
`number_format(style, scope, skip_years)`, `swap_entities(categories)`, `surface_noise(ops)`.

**Comparators:** `exact`, `token_f1`, `numeric_within(tol, relative, path)`,
`json_fields_equal(paths)`, `set_equal(path)`, `json_schema_equal`. Each one returns a score
from 0 to 1, which is what makes the self-variance baseline possible.

Some care went into avoiding false alarms. Typos never touch numbers or words shorter than
four letters, because a typo in "not" or "2019" changes the meaning, not the spelling. Number
formatting leaves years, phone numbers and IDs alone. Entity swaps only replace whole words
from a Kenyan name bank, apply consistently across the question and the documents, and map
the names back in the outputs before comparing.

## CLI

```
metamorph init [DIR]
metamorph run [--config F] [--relations a,b] [--limit N] [--gate] [--no-cache]
metamorph report [RUN_ID|latest] [--format json|junit] [--out F]
metamorph relations list
```

Each run writes `report.json` and `junit.xml` to `.metamorph/reports/<run-id>/`. In JUnit,
only blocking violations are `<failure>`s, so a CI test reporter turns red exactly when the
gate fails.

## Project layout

```
src/metamorph/
  cli.py  config.py  seeds.py  suite.py  gate.py  types.py
  adapters/      python and http targets
  transforms/    deterministic follow-up generators (+ registry)
  comparators/   agreement scorers (+ registry)
  relations/     builtin.yaml catalogue and resolver
  runner/        cache, executor (retries, concurrency), judge, engine
  storage/       SQLAlchemy Core schema (portable to Postgres) and repository
  reports/       report model, JSON and JUnit renderers
  data/          distractor bank, Kenyan entity bank
examples/rag_kenya/   demo RAG app with a planted bug
tests/                unit, Hypothesis property, runner (scripted fake target), end-to-end
```

## Development

```bash
pip install -e ".[dev]"
pytest -q                 # unit, property, runner and e2e tests, with no network or API keys
ruff check src tests examples && ruff format --check src tests examples
mypy
```

## Roadmap

- [x] **M1 Core engine:** types, 6 deterministic relations, python and http adapters,
      async runner, response cache, SQLite storage, JSON and JUnit reports, CLI and gate exit codes
- [ ] **M2** LLM transforms (paraphrase, Swahili, Sheng code-switching) and comparators
      (embeddings, LLM entailment judge), the self-variance report section, cost budget,
      HTML report
- [ ] **M3** Triage UI, per-relation precision, automatic promotion to BLOCKING
- [ ] **M4** Relation miner, plus a GitHub Action that comments on PRs
- [ ] **M5** Case study: violations found, false-alarm rate and cost per run

## Limitations

- `token_f1` is a lexical proxy. It under-scores correct paraphrased answers, which is why the
  built-ins start as WARNING. Embedding and entailment comparators arrive in M2.
- RAG relations need the app to accept injected context. A sealed endpoint that always
  retrieves for itself can only be tested with question-side relations.
- The response cache is keyed on target identity and code version. A remote target that
  changes behind the same URL needs `--no-cache` or a bumped `target.version`.
- Python callables run in worker threads, so they must be thread-safe at the configured
  concurrency.
