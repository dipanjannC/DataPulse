# Text2SQL — DataPulse

Ask a business question in plain English; get back the SQL and the rows. A Groq-backed
agent plans the query by *calling tools* against a **knowledge graph** of the schema
(tables, columns, join keys, canonical metrics), then runs read-only SQL against SQLite.

This stack is **self-contained** — it deploys on its own
(`render.yaml`). It spans five business domains: **Sales, IT, HR, Marketing, Security**.

---

## The four layers

Everything is driven by one contract — `metadata/schema.json` — which every layer reads.

```
metadata/schema.json   ← the CATALOG contract (50 tables · types · PKs · 40 FK edges · metrics)
        │  read by every layer
        ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │   GENERATE   │──▶│   QUALITY    │──▶│     LOAD     │──▶│   CONSUME    │
 │   datagen/   │   │   quality/   │   │ db/ + graph/ │   │agent/ + api/ │
 └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
  seeded CSVs,       validate CSVs      CSVs → SQLite      NL question →
  one module         against the        + Neo4j graph      tools over KG →
  per domain         schema (gate)      (schema meta)      SQL → rows
```

| Layer | Path | Entry point (the seam) | Does |
|---|---|---|---|
| **CATALOG** | `metadata/` | `utils.py`: `load_schema()`, `get_all_tables()`, `get_all_relationships()`, `get_domains()`, `get_metrics()` | The single source of truth: tables, column types, PKs, FK edges, canonical metric definitions. |
| **GENERATE** | `datagen/` | `generate(seed=42, domains=None, data_dir=...) -> {table: rows}` | Writes one CSV per table. Iterates the registry; fully seeded. |
| **QUALITY** | `quality/` | `validate_dataset(data_dir, schema=None) -> QualityReport` | Checks the CSVs conform to the schema (columns, types, PKs, non-null) and that referential integrity holds. |
| **LOAD** | `db/` + `knowledge_graph/` | `load(db_path, data_dir) -> LoadStats`; `build(uri, user, password)` | CSVs → SQLite (execution DB). Column/table metadata + FK edges → Neo4j (the schema graph the agent searches). |
| **CONSUME** | `agent/` + `api/` | `answer_question(question, *, groq_key, uri, user, password, db_path)`; FastAPI `/api/query` | The agent loop: discover schema via KG tools, write SQL, run it read-only, answer. |

The orchestrator `pipeline.py` runs GENERATE → QUALITY(gate) → LOAD in order.

---

## How a question is answered (CONSUME)

`run_agent` (in `agent/agent.py`) is a small, dependency-injected loop — it takes an
`llm_fn` and a `tool_fns` registry, so it's unit-tested with a fake model and fake tools
(no live Groq/Neo4j). The model works by calling three tools, in a loop, until it can
answer:

1. **`get_schema_context(question)`** — vector-search the Neo4j KG for the relevant tables,
   exact join keys, and canonical metric definitions. *Called first, always.*
2. **`sample_values(table, column)`** — peek at distinct values to resolve a categorical
   filter instead of guessing the literal.
3. **`run_sql(sql)`** — run a read-only `SELECT`/`WITH` query (guarded) and return rows.

The KG earns its keep here: reasoning is an explicit, inspectable **trace** of tool calls
rather than one opaque generation. `answer_question` wires the real Groq client + KG tools
and derives the prompt's domain list from `get_domains(load_schema())`.

---

## Run it

Prereqs: `uv`, and a `.env` with `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `GROQ_API_KEY`.

```bash
# 1. Build everything: generate → validate (gate) → SQLite → Neo4j KG
uv run python -m src.pipeline
#    --seed N          use a different RNG seed (default 42)
#    --fail-on-error   abort before load if the quality gate finds any violation
#                      (default is warn-only: log violations and continue)

# 2. Start the API (it also serves the UI)
uv run uvicorn src.api.main:app --reload --port 8000

# 3. Open the UI  →  http://localhost:8000/     (FastAPI serves the static frontend/)
```

The pipeline writes a `data/quality_report.json` (gitignored) each run — read it to see
exactly what the gate checked.

---

## Add a new domain  ← the payoff of the layering

Domains are pluggable. To add one (say **Finance**), you touch **three** places and nothing else:

1. **Declare it in the contract** — add a `Finance` block to `metadata/schema.json` with its
   `tables` (each column: `name`, `type` ∈ `INTEGER|REAL|TEXT|DATE|DATETIME`, `primary_key`,
   `nullable`, optional `foreign_key`) and a `relationships` list for its FK edges.

2. **Write the generator** — create `datagen/domains/finance.py`:

   ```python
   from __future__ import annotations
   import random
   import pandas as pd
   from faker import Faker
   from src.datagen.domains._common import rand_date  # rand_dt too, if needed

   def generate_finance(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
       # build DataFrames whose columns match the schema; draw ALL randomness
       # from the injected rng / fake — never module-level random or Faker.
       accounts = pd.DataFrame([{ "account_id": i + 1, ... } for i in range(100)])
       return {"accounts": accounts, ...}   # key = table name
   ```

3. **Register it** — add one line to `datagen/registry.py`:

   ```python
   DOMAIN_GENERATORS["Finance"] = generate_finance   # key MUST match the schema domain name
   ```

Then `uv run python -m src.pipeline`. That's it — SQLite loading, the Neo4j KG, the
agent's domain list, and validation all pick the new domain up automatically. The **quality
gate is what verifies your generator and your schema agree** (missing column? wrong type?
orphaned FK? it fails). `tests/text2sql/test_datagen_registry.py` also asserts the registry
covers every domain declared in `schema.json`, so a forgotten registration fails CI.

---

## Determinism

Generation is seeded **per run, injected** — there is no module-global RNG. Each
`generate(seed)` builds a fresh `random.Random(seed)` + `Faker(); fake.seed_instance(seed)`
and hands both to every domain generator. So two `generate(42)` calls in the same process
produce **byte-identical** CSVs (asserted in the tests). CSVs are written with LF line
endings explicitly, so output is identical across Windows/Linux/macOS too.

The tracked `data/*.csv` and `db/sales.db` therefore stay stable; they only ever change if
you deliberately change the seed or a generator — regenerate and commit that as one step.

---

## Quality gate

`validate_dataset` emits a `QualityReport` (`quality/reports.py`, harvested from
`src/quality/reports.py` is a standalone copy — no cross-layer import).. It checks, per the schema:

- **Schema conformance** — every declared column present and typed; PKs unique + non-null;
  `nullable: false` honored.
- **Referential integrity** — every non-null FK value resolves to a parent key (NULLs in
  nullable FKs are skipped; self-referential FKs like `categories.parent_category_id` are
  in scope). Nothing else enforces this — the SQLite DDL declares no `REFERENCES`.

Distributional (chi-square) checks are **deliberately skipped**: the schema declares no
expected distributions, and they would pull in `scipy`, which this lean deploy omits.

---

## Tests

```bash
uv run pytest tests/text2sql/      # all layers; no live Neo4j/Groq/SQLite (fakes only)
```

| File | Covers |
|---|---|
| `test_reports.py` | Report serialization round-trip |
| `test_quality_validator.py` | Each failure kind (missing column/table, dtype, null, dup PK) + referential integrity, on tiny in-memory schemas |
| `test_datagen_registry.py` | Same-process byte-identical determinism; registry ↔ schema agreement; generated data passes the gate |
| `test_pipeline.py` | The gate's abort/continue decision |
| `test_agent.py` | The `run_agent` loop, the read-only SQL guard, rate-limit handling, prompt-from-catalog |

---

## Deploy

`render.yaml` (repo root) runs `uvicorn src.api.main:app`; the build step pre-downloads
the `all-MiniLM-L6-v2` embedding model. `NEO4J_*` and `GROQ_API_KEY` are set as Render env vars.
