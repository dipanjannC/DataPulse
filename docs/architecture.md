# Architecture

This documents the **active** stack. For a task-oriented quickstart (run it, add a
domain), see [`../text2sql/README.md`](../text2sql/README.md). For the older `src/` graph stack,
see [legacy_src.md](legacy_src.md).

## Overview

The stack turns a plain-English business question into SQL and rows. A Groq-backed agent plans
the query by *calling tools* against a **Neo4j knowledge graph of the schema** (tables, columns,
join keys, canonical metrics), then executes read-only SQL against **SQLite**. It spans five
domains — Sales, IT, HR, Marketing, Security — and is self-contained (imports nothing from the other `src/` contexts,
deploys via `render.yaml`).

## The four layers

Everything is driven by one contract, `metadata/schema.json`, which every layer reads.

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

| Layer | Path | Entry-point seam | Responsibility |
|---|---|---|---|
| **CATALOG** | `metadata/` | `utils.py` (`load_schema`, `get_all_tables`, `get_all_relationships`, `get_domains`, `get_metrics`) | The contract: tables, column types, PKs, FK edges, canonical metric definitions. See [data_model.md](data_model.md). |
| **GENERATE** | `datagen/` | `generate(seed=42, domains=None, data_dir=...) -> {table: rows}` | Writes one seeded CSV per table by iterating a per-domain registry. |
| **QUALITY** | `quality/` | `validate_dataset(data_dir, schema=None) -> QualityReport` | Schema conformance + referential integrity over the CSVs. See [quality.md](quality.md). |
| **LOAD** | `db/` + `knowledge_graph/` | `load(db_path, data_dir) -> LoadStats`; `build(uri, user, password)` | CSVs → SQLite (execution DB); column metadata + FK edges → Neo4j (schema graph). |
| **CONSUME** | `agent/` + `api/` | `answer_question(question, *, groq_key, uri, user, password, db_path)`; FastAPI `/api/query` | Plan NL → SQL by calling KG tools; execute read-only. See [query_engine.md](query_engine.md). |

The orchestrator `pipeline.py` (`main() -> int`) runs GENERATE → QUALITY(gate) → LOAD in order.

## Two databases, two jobs

The single most important design point: **SQLite and Neo4j hold different things.**

- **SQLite (`db/sales.db`) — the execution store.** Holds the actual rows. The agent's `run_sql`
  tool queries it. It is the source of *answers*.
- **Neo4j (the knowledge graph) — the schema store.** Holds *metadata about the schema*: a node per
  table/column, FK edges between them, canonical metric definitions, and a vector index over column
  descriptions. The agent's `get_schema_context` tool searches it to discover *which* tables and join
  keys are relevant. It is the source of *the plan*, never of row data.

Row values live only in SQLite; the KG is unaffected by regenerating data (it is metadata-only). This
is why changing the generator seed never requires rebuilding the graph.

## Tech choices

| Concern | Choice | Rationale |
|---|---|---|
| Execution DB | SQLite (file, `db/sales.db`) | Zero-infra, tracked in-repo, fast read-only SELECTs |
| Schema graph | Neo4j (managed Aura) | Vector search over column metadata + FK-path traversal for join discovery |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), local | No API cost; runs in the deploy container |
| Agent LLM | Groq (`llama-3.3-70b-versatile`) | Fast tool-calling; the loop is provider-agnostic behind `llm_fn` |
| Data | pandas | CSV generation + bulk load |
| API / UI | FastAPI serving a static `frontend/` | One process serves `/api/*` and the UI at `/` |

## Internal seams (import direction within the codebase)

The layers depend one-directionally, mediated by the catalog:

- `metadata/` depends on nothing else (the contract).
- `datagen/` reads only `metadata/` (via the registry/generators); it does **not** import `quality`, `db`, or `agent`.
- `quality/` reads `metadata/` + its own `reports.py`; no DB, no network. `reports.py` is a **verbatim copy** of `src/datagen/reports.py` (copy, not import — the codebase imports nothing from the other `src/` contexts).
- `db/` and `knowledge_graph/` read `metadata/`.
- `agent/` uses `knowledge_graph/` (tools) + `metadata/` (prompt domain list); `run_agent` itself is provider-agnostic.
- `pipeline.py` (orchestrator) is the only module that wires generate + quality + load together.

## See also

- [`../text2sql/README.md`](../text2sql/README.md) — quickstart, and how to add a new domain
- [data_model.md](data_model.md) · [query_engine.md](query_engine.md) · [agents_design.md](agents_design.md) · [quality.md](quality.md)
- [legacy_src.md](legacy_src.md) — the retiring `src/` stack
