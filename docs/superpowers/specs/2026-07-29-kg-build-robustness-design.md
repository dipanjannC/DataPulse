# KG Build Robustness — Design

- **Date:** 2026-07-29
- **Status:** Approved (design); pending implementation plan
- **Component:** `src/knowledge_graph/` (builder), `src/metadata/` (new validator), `src/api/main.py` (health surface)
- **Related review:** the graph loader is canonical in *source* (built from `schema.json` via `metadata.utils`) but not robust in *behavior*.

## Problem

The Neo4j knowledge graph is built by `src/knowledge_graph/builder.py` from `schema.json` (it does **not** read the flat CSVs — those go to SQLite via `src/db/loader.py`). The build path can corrupt the graph the retriever then feeds the LLM:

1. **Silent bad / missing join edges.** `_upsert_fk_relationships` and `_upsert_table_references` resolve endpoints by `MATCH`; a `MATCH` that binds nothing makes the following `MERGE` a silent no-op. Worse, `_upsert_table_references` gates only on *table* existence, so a relationship with a bad **column** name still writes a `REFERENCES` edge carrying bogus join keys — which the retriever hands the LLM as an explicit `JOIN ... ON` a non-existent column. Nothing upstream catches this: `quality/validator.py` checks CSV-vs-schema, never schema-internal relationship consistency. This bites even on a first clean build.

2. **Never prunes → orphans certified fresh.** Every write is `MERGE` and nothing wipes first, so removing a table/column/relationship from `schema.json` and rebuilding leaves orphan nodes/edges — including live vector-index entries and `REFERENCES` edges the join planner will still traverse. `_upsert_meta` then re-stamps the new fingerprint, so `is_kg_fresh` returns `True` and `/api/health` reports green over a dirty graph.

Secondary: per-row round-trips to a remote Aura instance (hundreds of sequential `session.run` calls); `driver.close()` sits outside a `finally` (leaks on exception).

## Goals

- A broken relationship in `schema.json` can never produce a wrong or bogus join edge in the graph.
- A rebuild leaves **no orphans** — the graph reflects exactly the current `schema.json`.
- The graph is **never dark** during a rebuild, and an interrupted build self-heals.
- Broken relationships are **skipped, not fatal**, and surfaced loudly and durably.

## Non-goals (explicitly out of scope)

- CLI-form hygiene beyond what integrity requires (`print`→logger everywhere, `main() -> int`/argparse, `os.getenv` migration). Deferred to a later "Full KG hardening" pass.
- The planner/writer module split (brainstorm approach B).
- Retry loops around the driver.
- A single-transaction atomic-snapshot swap (rejected: free-tier Aura transaction-memory and vector-index risk; not needed for the chosen availability model).

## Constraints & decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Correctness + integrity | Validate relationships; clean rebuild; atomic/interruptible build. |
| Broken relationship | **Warn + skip** (both edges) | Fits the repo's graceful-degradation ethos; a single authoring bug shouldn't block the whole rebuild. Skip must drop *both* `FOREIGN_KEY` and `REFERENCES`, or the corrupting edge still leaks. |
| Availability | **Never-dark** (mixed OK) | Rebuilds are manual/dev actions; the graph must never go empty, but a brief mixed old/new window mid-rebuild is acceptable. Consistent-snapshot was rejected as over-engineering. |
| Environment | Single-database Aura (assumed) | Rules out building into a second DB and swapping. Confirm if on a multi-DB tier. |

## Architecture — three units

### Unit 1 · Catalog integrity check — `src/metadata/validate.py` (new, pure)

Answers one question: does the catalog reference itself consistently?

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SkippedRelationship:
    relationship: dict
    reason: str            # e.g. "from_column 'orders.custommer_id' is not a declared column"

@dataclass(frozen=True)
class RelationshipCheck:
    valid: list[dict]
    skipped: list[SkippedRelationship]

    @property
    def skip_reasons(self) -> list[str]: ...   # human-readable, for logs / BuildStats / Meta

def check_relationships(schema: dict) -> RelationshipCheck: ...
```

Logic: build the set of declared table names and column keys (`{table.column}`) from the schema; for each relationship, require `from_table`/`to_table` to be declared tables and `from_column`/`to_column` to be declared columns of their respective tables. Any failure → `skipped` with a precise reason; else → `valid`. Self-referential relationships (e.g. `employees.manager_id → employees.employee_id`) are valid.

- **Depends on:** stdlib + `metadata.utils` only. No Neo4j, no pandas, no embeddings.
- **Consumed by:** the builder's preflight (this spec); optionally the pipeline later.
- **Convention:** stdlib `@dataclass(frozen=True)` (internal result object — we control inputs, so pydantic buys nothing).

### Unit 2 · Never-dark graph builder — `src/knowledge_graph/builder.py` (refactor in place)

```python
@dataclass(frozen=True)
class BuildStats:
    domains: int
    tables: int
    columns: int
    fk_edges: int          # valid relationships written
    metrics: int
    skipped: list[str]     # skip reasons
    fingerprint: str
    build_id: str

def build(uri: str, user: str, password: str, *,
          schema: dict | None = None,
          build_id: str | None = None) -> BuildStats: ...
```

- `schema` and `build_id` are injectable **purely for testing** (mirrors datagen's injected-seed determinism); both default to real values (`load_schema()`, `uuid4().hex`).
- **`build_id` is a per-run nonce, not the fingerprint.** The fingerprint is stable across rebuilds of the same schema and so cannot distinguish this run's nodes from the last run's; the nonce can. This is what makes the sweep correct.
- Returns `BuildStats` (mirrors `db/loader.py`'s `LoadStats`) so the pipeline can log a summary. Replaces the current `print(...)`.
- **Depends on:** `neo4j`, `embeddings.embed`, Unit 1, `metadata.utils`, `freshness`.

### Unit 3 · Freshness & health surface — `freshness.py` + `_upsert_meta` + `/api/health` (extend)

- `_upsert_meta` writes two new properties: `skipped_relationships` (int count) and `skipped_relationship_details` (`list[str]`), plus `build_id`.
- `_kg_probe` (`src/api/main.py:56`) extends its Cypher to also `RETURN m.skipped_relationships AS skipped` and includes it in its return dict.
- `health()` (`src/api/main.py:89`) adds `kg_skipped_relationships` to the payload, read defensively via `probe.get("skipped")` so existing mocked probes keep working.
- `is_kg_fresh` / `kg_fingerprint` are **unchanged**. Freshness and validity stay orthogonal: the fingerprint hashes the whole schema, so `kg_fresh` still means "graph matches this schema"; the skip count is the separate "schema has authoring bugs" signal.

## Data flow — the build sequence

```
1. Preflight     check_relationships(schema) -> (valid, skipped)      [pure, no Neo4j]
                 logger.warning per skip
2. Embeddings    build_{column,table,domain}_embeddings(schema)        [unchanged]
3. Schema setup  constraints + vector indexes, IF NOT EXISTS           [idempotent, unchanged]
4. Upsert        UNWIND-batched MERGE: domains, tables, columns,
                 metrics, HAS_TABLE/HAS_COLUMN, and only-valid
                 FOREIGN_KEY/REFERENCES; every node & edge SET build_id
5. Sweep         DETACH DELETE nodes whose build_id <> this run;
                 DELETE edges whose build_id <> this run   (excludes :Meta)
6. Meta LAST     stamp fingerprint + skipped summary + build_id + counts
7. finally       driver.close()
```

- **Never-dark:** step 4 is upsert-in-place (`MERGE`), never delete-first, so readers always hit a working graph. During steps 4–5 a reader may briefly see some new + some old nodes (the accepted mixed window); never empty.
- **Orphan-killer:** step 5 removes exactly what this run did not touch — a deleted table/column/relationship disappears from the graph *and* its vector-index entries.
- **Self-heal on interruption:** die before step 5 → mixed graph, `Meta` still old → health reports stale → next run sweeps and fixes. Die between 5 and 6 → graph correct, `Meta` old → stale → harmless re-confirm. No interruption can empty the graph.
- **Batching:** one `UNWIND $rows` call per node/edge type inside `session.execute_write(...)` units of work, replacing the per-row round-trips.
- **Transaction boundaries:** steps 4, 5, and 6 are separate write transactions in order — **the upserts commit before the sweep runs, and the sweep commits before `Meta` is stamped**. This is deliberate, not a single mega-transaction (which is the rejected atomic-snapshot approach): it keeps each transaction small (free-tier memory) and preserves the self-heal ordering. Within step 4, the node/edge upserts may share one transaction or be split per type; correctness does not depend on which.

### Representative Cypher

Column upsert (batched, stamped):

```cypher
UNWIND $columns AS c
MERGE (n:Column {key: c.key})
SET n.name = c.name, n.table_name = c.table_name, n.domain = c.domain,
    n.description = c.description, n.data_type = c.data_type,
    n.is_primary_key = c.is_primary_key, n.aliases = c.aliases,
    n.allowed_values = c.allowed_values, n.embedding = c.embedding,
    n.build_id = $build_id
WITH c, n MATCH (t:Table {name: c.table_name})
MERGE (t)-[r:HAS_COLUMN]->(n) SET r.build_id = $build_id
```

Valid-only REFERENCES (preflight guarantees both columns exist → no bogus edge):

```cypher
UNWIND $refs AS x
MATCH (a:Table {name: x.from_table}), (b:Table {name: x.to_table})
MERGE (a)-[r:REFERENCES {from_column: x.from_column, to_column: x.to_column}]->(b)
SET r.build_id = $build_id
```

Sweep:

```cypher
MATCH (n) WHERE (n:Domain OR n:Table OR n:Column OR n:Metric)
  AND coalesce(n.build_id, '') <> $build_id
DETACH DELETE n;

MATCH ()-[r:HAS_TABLE|HAS_COLUMN|FOREIGN_KEY|REFERENCES]->()
WHERE coalesce(r.build_id, '') <> $build_id
DELETE r
```

`DETACH DELETE` handles edges incident to swept nodes; the explicit edge sweep handles edges between two survivors whose relationship (or REFERENCES join-key signature) was removed/changed.

## Error handling & edge cases

1. **Skip completeness (core fix):** a relationship failing preflight is excluded from *both* the `$fks` and `$refs` payloads — neither edge is written. Because preflight guarantees endpoint columns exist, every surviving `REFERENCES` edge is provably safe.
2. **Loud + durable, three surfaces:** `logger.warning` at build time; `skipped_relationships` count + details on `Meta`; `kg_skipped_relationships` on `/api/health`; `BuildStats.skipped` into the pipeline summary log.
3. **Driver lifecycle:** `try/finally: driver.close()` around the build.
4. **Transient Neo4j failure mid-build:** exception propagates (build fails), `Meta` not restamped → health stale; previous graph intact and serving (never delete-first); next run self-heals. No retry loops.
5. **Sweep safety:** scoped to KG labels, excludes `:Meta`; first-ever build sweeps nothing; a no-change rebuild sweeps nothing; sweep runs only after all upserts.
6. **Degenerate schemas:** empty domain → Domain node, no children; self-referential relationship → valid, written as a `REFERENCES` self-loop, swept by `build_id`; every relationship invalid → disconnected tables + loud skip report, never-dark still holds.
7. **Fingerprint ⊥ skip:** a schema with a broken relationship still hashes stably, so re-running it is idempotent and `kg_fresh` stays honest; the skip count is the separate correctness signal.

## Testing (all fakes, no live Neo4j — per repo rule)

**New `tests/text2sql/test_validate.py`:**
- valid schema → all valid, none skipped
- bad `from_column` → skipped, reason names the column
- bad `to_table` → skipped, reason names the table
- endpoint present in the CSV but not declared in schema → skipped (the precise gap `quality/validator.py` misses today)
- self-referential relationship → valid

**Extend `tests/text2sql/test_builder.py`** (drive with the existing `_FakeSession`):
- **Skip completeness (key regression):** an invalid relationship emits no `FOREIGN_KEY` and no `REFERENCES` write for it
- **`build_id` stamping:** every node/edge payload carries the injected `build_id`
- **Sweep:** emitted after upserts, targets `build_id <> $build_id`, scoped to KG labels, excludes `:Meta`
- **Meta last:** the `Meta` upsert is the final write; carries fingerprint + skipped count + build_id + counts
- **UNWIND batching:** writes are batched payloads, not one call per column
- existing `allowed_values` / `aliases` tests still pass

**Extend `tests/text2sql/test_freshness.py`:** skipped relationships don't affect the fingerprint; `is_kg_fresh` semantics unchanged.

**Extend `tests/text2sql/test_main.py`:** `/api/health` surfaces `kg_skipped_relationships` (mock `_kg_probe` to return a skip count); existing three health tests still pass (defensive `.get`).

**Determinism:** `build_id` is a per-run nonce, so tests inject it via `build_id=`. The tracked-CSV determinism gate is untouched (datagen is not modified).

## Rollout

- Pure code change to the builder + a new validator module; the tracked `src/data/*.csv` and `src/db/sales.db` are **not** affected.
- After merge, rebuild the KG once (`uv run python -m src.knowledge_graph.builder` or `/run-pipeline`); the first post-change build sweeps any pre-existing orphans.
- Verify: `uv run pytest tests/text2sql/`; then `/api/health` reports `kg_fresh: true` and `kg_skipped_relationships: 0` on a clean schema.

## Open questions / assumptions

- **Aura tier:** assumed single-database. If multi-DB, a true snapshot swap becomes cheap — but never-dark is still sufficient for the stated need.
- **Skip-detail size:** `skipped_relationship_details` stored as `list[str]` on `Meta` (relationships are few); revisit only if it ever grows large.
