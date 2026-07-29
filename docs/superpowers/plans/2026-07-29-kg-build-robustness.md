# KG Build Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Neo4j KG build corruption-proof — validate schema relationships before building (skip the broken ones loudly), rebuild without orphans, and never leave the graph dark or half-stamped.

**Architecture:** A new pure `metadata/validate.py` partitions schema relationships into valid/skipped. The builder is refactored to write only valid relationships, `UNWIND`-batch every upsert, stamp each node/edge with a per-run `build_id`, sweep anything the run didn't touch (orphan-killer), and stamp `Meta` last (so an interrupted build self-heals). `/api/health` gains a skipped-relationship count. See the design spec: `docs/superpowers/specs/2026-07-29-kg-build-robustness-design.md`.

**Tech Stack:** Python 3.12, `neo4j` driver (Cypher), `sentence-transformers` (embeddings), `pytest`, `uv`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Package manager:** `uv` only. Run tests with `uv run pytest`. Never pip/poetry/conda.
- **Typing:** `from __future__ import annotations` at the top of every `src/` module; modern generics (`list[X]`, `dict[K, V]`, `X | None`); never import `Optional`/`List`/`Dict` from `typing`.
- **Logging & I/O:** `logger = logging.getLogger(__name__)` at module top; **no `print()` in `src/`**; `%s` placeholders in log calls, not f-strings.
- **Dataclasses:** value/result objects are frozen; **stdlib `@dataclass(frozen=True)` for pure internal result objects** (we control their inputs).
- **Tests:** one file per source module under `tests/text2sql/`; fakes defined inline as private `_Prefixed` classes; **mock at boundaries only (driver), never patch internals**; **no test depends on a live Neo4j/Groq**.
- **Determinism:** the builder's `build_id` is a per-run nonce, so tests **inject** it via the `build_id=` kwarg.
- **Do not modify `src/datagen/` or `src/data/*.csv`** — the tracked-CSV determinism gate must stay untouched (this work is metadata-only).
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `src/metadata/validate.py` | Create | Pure schema-internal consistency check: partition relationships into valid/skipped. |
| `tests/text2sql/test_validate.py` | Create | Unit tests for `check_relationships`. |
| `src/knowledge_graph/builder.py` | Modify (rewrite) | Never-dark build: preflight-skip, `UNWIND` batching, `build_id` stamp, sweep, `Meta`-last, `BuildStats`, `try/finally`. |
| `tests/text2sql/test_builder.py` | Modify (rewrite) | Fake-session tests: skip-completeness, `build_id` stamping, sweep, `Meta`-last, `BuildStats`. |
| `src/pipeline.py` | Modify (`build()` call site, ~L94-100) | Log the returned `BuildStats` (tables/columns/edges/skipped). |
| `tests/text2sql/test_freshness.py` | Modify (add one test) | A broken-relationship schema still fingerprints deterministically (idempotent rebuild). |
| `src/api/main.py` | Modify (`_kg_probe` ~L56-86, `health` ~L89-105) | Read + surface `kg_skipped_relationships`. |
| `tests/text2sql/test_main.py` | Modify (add one test) | `/api/health` surfaces the skip count. |

---

## Task 1: Catalog integrity check (`metadata/validate.py`)

**Files:**
- Create: `src/metadata/validate.py`
- Test: `tests/text2sql/test_validate.py`

**Interfaces:**
- Consumes: `src.metadata.utils.get_all_tables`, `get_all_relationships` (existing).
- Produces:
  - `check_relationships(schema: dict) -> RelationshipCheck`
  - `@dataclass(frozen=True) RelationshipCheck` with `valid: list[dict]`, `skipped: list[SkippedRelationship]`, and property `skip_reasons -> list[str]`.
  - `@dataclass(frozen=True) SkippedRelationship` with `relationship: dict`, `reason: str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/text2sql/test_validate.py`:

```python
"""check_relationships: schema-internal consistency of schema.json relationships."""

from __future__ import annotations

from src.metadata.validate import check_relationships


def _schema(relationships: list[dict]) -> dict:
    return {
        "version": "1",
        "domains": [{
            "name": "Sales", "description": "d",
            "tables": [
                {"name": "orders", "description": "", "columns": [
                    {"name": "order_id", "type": "INTEGER", "primary_key": True},
                    {"name": "customer_id", "type": "INTEGER"},
                ]},
                {"name": "customers", "description": "", "columns": [
                    {"name": "customer_id", "type": "INTEGER", "primary_key": True},
                ]},
                {"name": "employees", "description": "", "columns": [
                    {"name": "employee_id", "type": "INTEGER", "primary_key": True},
                    {"name": "manager_id", "type": "INTEGER"},
                ]},
            ],
            "relationships": relationships,
        }],
    }


_VALID = {"from_table": "orders", "from_column": "customer_id",
          "to_table": "customers", "to_column": "customer_id"}


def test_valid_relationship_is_kept():
    check = check_relationships(_schema([_VALID]))
    assert check.valid == [_VALID]
    assert check.skipped == []


def test_bad_from_column_is_skipped_with_reason_naming_the_column():
    bad = {**_VALID, "from_column": "custommer_id"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert len(check.skipped) == 1
    assert "orders.custommer_id" in check.skipped[0].reason
    assert "from_column" in check.skipped[0].reason


def test_bad_to_table_is_skipped_with_reason_naming_the_table():
    bad = {**_VALID, "to_table": "custmers"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert "custmers" in check.skipped[0].reason
    assert "to_table" in check.skipped[0].reason


def test_endpoint_in_data_but_not_declared_in_schema_is_skipped():
    # 'notes' is not a declared column on orders -> the exact gap the quality
    # validator misses today (it only checks CSV-vs-schema).
    bad = {**_VALID, "from_column": "notes"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert "orders.notes" in check.skipped[0].reason


def test_self_referential_relationship_is_valid():
    self_ref = {"from_table": "employees", "from_column": "manager_id",
                "to_table": "employees", "to_column": "employee_id"}
    check = check_relationships(_schema([self_ref]))
    assert check.valid == [self_ref]
    assert check.skipped == []


def test_skip_reasons_property_lists_all_reasons():
    bad1 = {**_VALID, "from_column": "nope"}
    bad2 = {**_VALID, "to_table": "nope"}
    check = check_relationships(_schema([_VALID, bad1, bad2]))
    assert len(check.valid) == 1
    assert len(check.skip_reasons) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/text2sql/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.metadata.validate'`.

- [ ] **Step 3: Write the implementation**

Create `src/metadata/validate.py`:

```python
"""Catalog integrity — schema-internal consistency of schema.json.

Distinct from ``quality/validator.py`` (which checks generated CSVs against the
schema): this validates that the *catalog references itself* consistently, so a
relationship can never name a table or column that isn't declared. The KG
builder consumes this to skip broken relationships instead of silently writing
bogus join edges.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.metadata.utils import get_all_relationships, get_all_tables


@dataclass(frozen=True)
class SkippedRelationship:
    relationship: dict
    reason: str


@dataclass(frozen=True)
class RelationshipCheck:
    valid: list[dict]
    skipped: list[SkippedRelationship]

    @property
    def skip_reasons(self) -> list[str]:
        return [s.reason for s in self.skipped]


def check_relationships(schema: dict) -> RelationshipCheck:
    """Partition schema relationships into valid vs skipped. A relationship is
    valid only when both endpoints name a declared table AND a declared column
    on that table."""
    tables = get_all_tables(schema)
    table_names = {t["name"] for t in tables}
    columns = {t["name"]: {c["name"] for c in t["columns"]} for t in tables}

    valid: list[dict] = []
    skipped: list[SkippedRelationship] = []
    for rel in get_all_relationships(schema):
        reason = _endpoint_error(rel, table_names, columns)
        if reason is None:
            valid.append(rel)
        else:
            skipped.append(SkippedRelationship(relationship=rel, reason=reason))
    return RelationshipCheck(valid=valid, skipped=skipped)


def _endpoint_error(
    rel: dict, table_names: set[str], columns: dict[str, set[str]]
) -> str | None:
    for side in ("from", "to"):
        table = rel.get(f"{side}_table")
        column = rel.get(f"{side}_column")
        if table not in table_names:
            return f"{side}_table '{table}' is not a declared table"
        if column not in columns.get(table, set()):
            return f"{side}_column '{table}.{column}' is not a declared column"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/text2sql/test_validate.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/metadata/validate.py tests/text2sql/test_validate.py
git commit -m "feat(metadata): schema relationship integrity check

check_relationships() partitions schema.json relationships into valid vs
skipped (endpoint not a declared table/column) — the source-of-truth the KG
builder uses to skip broken join edges instead of writing bogus ones.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Never-dark builder (`knowledge_graph/builder.py`)

**Files:**
- Modify (rewrite): `src/knowledge_graph/builder.py`
- Modify (rewrite): `tests/text2sql/test_builder.py`
- Modify: `src/pipeline.py` (the `build()` call site, ~L94-100)
- Modify: `tests/text2sql/test_freshness.py` (add one test)

**Interfaces:**
- Consumes: `src.metadata.validate.check_relationships` (Task 1); `src.embeddings.embed.{build_column_embeddings, build_table_embeddings, build_domain_embeddings, MODEL_NAME}`; `src.knowledge_graph.freshness.kg_fingerprint`; `src.metadata.utils.{get_all_tables, get_domains, get_metrics, load_schema}`.
- Produces:
  - `build(uri: str, user: str, password: str, *, schema: dict | None = None, build_id: str | None = None) -> BuildStats`
  - `_run_build(session, schema: dict, check: RelationshipCheck, embeddings: dict, build_id: str) -> BuildStats` (pure orchestration over a session-like boundary)
  - `@dataclass(frozen=True) BuildStats` with `domains, tables, columns, fk_edges, metrics: int`, `skipped: list[str]`, `fingerprint: str`, `build_id: str`
  - helpers: `_upsert_domains`, `_upsert_tables`, `_upsert_columns`, `_upsert_metrics`, `_upsert_foreign_keys`, `_upsert_references`, `_sweep`, `_upsert_meta` (all take `(session, ..., build_id)`), and the unchanged `_create_constraints`, `_create_vector_indexes`.

**Note on batching:** each node/edge type is one `session.run("UNWIND $rows ...")` (auto-commit). This removes the per-row round-trips (the finding) while keeping each phase its own transaction — so `Meta`-last still means an interrupted build self-heals — and keeps the fake-session (`.run`) test seam identical to today. `session.execute_write` is deliberately not used.

- [ ] **Step 1: Rewrite the test file (failing tests)**

Replace the entire contents of `tests/text2sql/test_builder.py`:

```python
"""KG builder: batched UNWIND upserts, build_id stamping, orphan sweep,
valid-only relationship edges, and the Meta build stamp. Driven against a fake
session that records Cypher + params in order — no live Neo4j."""

from __future__ import annotations

from src.embeddings.embed import MODEL_NAME
from src.knowledge_graph.builder import (
    _run_build,
    _sweep,
    _upsert_columns,
)
from src.knowledge_graph.freshness import kg_fingerprint
from src.metadata.utils import get_all_tables
from src.metadata.validate import check_relationships


class _FakeSession:
    """Records every session.run(query, **params) call in order. Executes nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return None


def _schema() -> dict:
    return {
        "version": "1",
        "domains": [{
            "name": "Sales", "description": "sales domain",
            "tables": [
                {"name": "orders", "description": "orders", "columns": [
                    {"name": "order_id", "type": "INTEGER", "description": "id", "primary_key": True},
                    {"name": "customer_id", "type": "INTEGER", "description": "fk"},
                    {"name": "status", "type": "TEXT", "description": "status",
                     "allowed_values": ["Pending", "Shipped"]},
                ]},
                {"name": "customers", "description": "customers", "columns": [
                    {"name": "customer_id", "type": "INTEGER", "description": "id", "primary_key": True},
                ]},
            ],
            "relationships": [
                {"from_table": "orders", "from_column": "customer_id",
                 "to_table": "customers", "to_column": "customer_id"},
                {"from_table": "orders", "from_column": "custommer_id",   # typo -> invalid
                 "to_table": "customers", "to_column": "customer_id"},
            ],
        }],
    }


_EMB = {"column": {}, "table": {}, "domain": {}}


def _run(session: _FakeSession, schema: dict, build_id: str = "BID"):
    return _run_build(session, schema, check_relationships(schema), _EMB, build_id)


def _rows_for(session: _FakeSession, needle: str) -> list[dict]:
    return next(p["rows"] for q, p in session.calls if needle in q and "rows" in p)


def test_invalid_relationship_writes_no_fk_or_reference_edge():
    session = _FakeSession()
    _run(session, _schema())

    fk_rows = _rows_for(session, "FOREIGN_KEY")    # only the FK upsert has both this + a rows param
    ref_rows = _rows_for(session, "REFERENCES")    # (sweep queries carry no rows param)
    assert fk_rows == [{"fk_key": "orders.customer_id", "pk_key": "customers.customer_id"}]
    assert len(ref_rows) == 1 and ref_rows[0]["from_column"] == "customer_id"

    blob = str(fk_rows) + str(ref_rows)
    assert "custommer_id" not in blob   # the typo'd endpoint is never written, on either edge


def test_every_batched_upsert_carries_build_id():
    session = _FakeSession()
    _run(session, _schema(), build_id="XYZ")

    upserts = [(q, p) for q, p in session.calls if "rows" in p]
    assert upserts
    for q, p in upserts:
        assert p["build_id"] == "XYZ"
        assert "build_id = $build_id" in q


def test_allowed_values_written_on_column_rows():
    session = _FakeSession()
    _upsert_columns(session, get_all_tables(_schema()), {}, "BID")

    by_key = {r["key"]: r for r in _rows_for(session, "MERGE (c:Column")}
    assert by_key["orders.status"]["allowed_values"] == ["Pending", "Shipped"]
    assert by_key["orders.order_id"]["allowed_values"] == []


def test_sweep_deletes_by_build_id_and_never_touches_meta():
    session = _FakeSession()
    _sweep(session, "BID")

    node_q = next(q for q, p in session.calls if "DETACH DELETE" in q)
    assert "coalesce(n.build_id, '') <> $build_id" in node_q
    assert ":Meta" not in node_q
    for _, p in session.calls:
        assert p["build_id"] == "BID"


def test_meta_is_stamped_last_with_skip_summary():
    session = _FakeSession()
    schema = _schema()
    _run(session, schema, build_id="BID")

    last_q, last_p = session.calls[-1]
    assert "MERGE (m:Meta {key: 'kg'})" in last_q
    assert last_p["fingerprint"] == kg_fingerprint(schema, MODEL_NAME)
    assert last_p["build_id"] == "BID"
    assert last_p["skipped_count"] == 1
    assert any("custommer_id" in d for d in last_p["skipped_details"])


def test_sweep_runs_after_upserts_and_before_meta():
    session = _FakeSession()
    _run(session, _schema())
    kinds = [q for q, _ in session.calls]
    last_upsert = max(i for i, q in enumerate(kinds) if "rows" in session.calls[i][1])
    sweep = next(i for i, q in enumerate(kinds) if "DETACH DELETE" in q)
    meta = next(i for i, q in enumerate(kinds) if "MERGE (m:Meta" in q)
    assert last_upsert < sweep < meta


def test_run_build_returns_stats_with_skips():
    session = _FakeSession()
    stats = _run(session, _schema(), build_id="BID")
    assert stats.tables == 2
    assert stats.columns == 4          # 3 on orders + 1 on customers
    assert stats.fk_edges == 1         # only the valid relationship
    assert stats.skipped == list(check_relationships(_schema()).skip_reasons)
    assert stats.build_id == "BID"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/text2sql/test_builder.py -v`
Expected: FAIL — `ImportError` (`_run_build`, `_sweep`, `_upsert_columns` don't exist yet).

- [ ] **Step 3: Rewrite the builder**

Replace the entire contents of `src/knowledge_graph/builder.py`:

```python
"""Step 5 — Neo4j Knowledge Graph builder.

Node model
----------
(:Domain {name, description, embedding, build_id})
(:Table  {name, description, domain, embedding, build_id})
(:Column {key, name, table_name, domain, description, data_type, is_primary_key,
          aliases, allowed_values, embedding, build_id})
(:Metric {name, expression, description, tables, build_id})
(:Meta   {key, schema_fingerprint, model, built_at, build_id, domains, tables,
          columns, skipped_relationships, skipped_relationship_details})

Relationship model
------------------
(:Domain)-[:HAS_TABLE {build_id}]->(:Table)
(:Table)-[:HAS_COLUMN {build_id}]->(:Column)
(:Column)-[:FOREIGN_KEY {build_id}]->(:Column)
(:Table)-[:REFERENCES {from_column, to_column, build_id}]->(:Table)

Robustness model
----------------
Every node/edge is stamped with a per-run ``build_id`` (a nonce, NOT the
fingerprint — the fingerprint is stable across rebuilds of the same schema and
so cannot tell one run's nodes from the last). After upserting, ``_sweep``
deletes anything not carrying this run's ``build_id`` (the orphan-killer). The
graph is never deleted-first, so it is never dark; ``Meta`` is stamped LAST so
an interrupted build self-heals (old fingerprint stands -> health reports stale
-> next run fixes it). Only relationships that pass ``check_relationships`` are
written, so a broken relationship leaks neither a FOREIGN_KEY nor a REFERENCES
edge.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from neo4j import GraphDatabase

from src.embeddings.embed import (
    MODEL_NAME,
    build_column_embeddings,
    build_domain_embeddings,
    build_table_embeddings,
)
from src.knowledge_graph.freshness import kg_fingerprint
from src.metadata.utils import (
    get_all_tables,
    get_domains,
    get_metrics,
    load_schema,
)
from src.metadata.validate import RelationshipCheck, check_relationships

logger = logging.getLogger(__name__)

VECTOR_DIM = 384   # all-MiniLM-L6-v2


@dataclass(frozen=True)
class BuildStats:
    domains: int
    tables: int
    columns: int
    fk_edges: int
    metrics: int
    skipped: list[str]
    fingerprint: str
    build_id: str


def build(
    uri: str,
    user: str,
    password: str,
    *,
    schema: dict | None = None,
    build_id: str | None = None,
) -> BuildStats:
    schema = load_schema() if schema is None else schema
    build_id = uuid.uuid4().hex if build_id is None else build_id

    check = check_relationships(schema)
    for reason in check.skip_reasons:
        logger.warning("Skipping invalid relationship: %s", reason)

    embeddings = {
        "column": build_column_embeddings(schema),
        "table": build_table_embeddings(schema),
        "domain": build_domain_embeddings(schema),
    }

    driver = GraphDatabase.driver(
        uri, auth=(user, password),
        notifications_disabled_classifications=["DEPRECATION"],
    )
    try:
        with driver.session() as session:
            stats = _run_build(session, schema, check, embeddings, build_id)
    finally:
        driver.close()

    logger.info(
        "Knowledge Graph built: %d domains | %d tables | %d columns | %d FK edges | "
        "%d metrics | %d skipped | fingerprint %s",
        stats.domains, stats.tables, stats.columns, stats.fk_edges,
        stats.metrics, len(stats.skipped), stats.fingerprint,
    )
    return stats


def _run_build(session, schema: dict, check: RelationshipCheck,
               embeddings: dict, build_id: str) -> BuildStats:
    """Pure orchestration over a session-like boundary (unit-tested with a fake).
    Order is load-bearing: upsert everything under build_id, THEN sweep anything
    not touched, THEN stamp Meta LAST so an interrupted build self-heals."""
    tables = get_all_tables(schema)
    domains = get_domains(schema)
    metrics = get_metrics(schema)

    _create_constraints(session)
    _create_vector_indexes(session)

    _upsert_domains(session, domains, embeddings["domain"], build_id)
    _upsert_tables(session, tables, embeddings["table"], build_id)
    _upsert_columns(session, tables, embeddings["column"], build_id)
    _upsert_metrics(session, metrics, build_id)
    _upsert_foreign_keys(session, check.valid, build_id)
    _upsert_references(session, check.valid, build_id)

    _sweep(session, build_id)

    fingerprint = kg_fingerprint(schema, MODEL_NAME)
    _upsert_meta(session, schema, check, build_id, fingerprint)  # LAST

    return BuildStats(
        domains=len(domains),
        tables=len(tables),
        columns=sum(len(t["columns"]) for t in tables),
        fk_edges=len(check.valid),
        metrics=len(metrics),
        skipped=list(check.skip_reasons),
        fingerprint=fingerprint,
        build_id=build_id,
    )


# ── schema setup ──────────────────────────────────────────────────────────────

def _create_constraints(session) -> None:
    session.run(
        "CREATE CONSTRAINT domain_name_unique IF NOT EXISTS "
        "FOR (d:Domain) REQUIRE d.name IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT table_name_unique IF NOT EXISTS "
        "FOR (t:Table) REQUIRE t.name IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT column_key_unique IF NOT EXISTS "
        "FOR (c:Column) REQUIRE c.key IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT metric_name_unique IF NOT EXISTS "
        "FOR (m:Metric) REQUIRE m.name IS UNIQUE"
    )


def _create_vector_indexes(session) -> None:
    for index_name, label, prop in (
        ("column_embedding", "Column", "embedding"),
        ("table_embedding",  "Table",  "embedding"),
        ("domain_embedding", "Domain", "embedding"),
    ):
        session.run(f"""
            CREATE VECTOR INDEX {index_name} IF NOT EXISTS
            FOR (n:{label}) ON (n.{prop})
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {VECTOR_DIM},
                    `vector.similarity_function`: 'cosine'
                }}
            }}
        """)


# ── node upserts (batched, build_id-stamped) ────────────────────────────────────

def _upsert_domains(session, domains: list[dict], domain_emb: dict, build_id: str) -> None:
    rows = [
        {"name": d["name"], "description": d["description"],
         "embedding": domain_emb.get(d["name"], [])}
        for d in domains
    ]
    session.run(
        """
        UNWIND $rows AS row
        MERGE (d:Domain {name: row.name})
        SET d.description = row.description,
            d.embedding   = row.embedding,
            d.build_id    = $build_id
        """,
        rows=rows, build_id=build_id,
    )


def _upsert_tables(session, tables: list[dict], table_emb: dict, build_id: str) -> None:
    rows = [
        {"name": t["name"], "description": t["description"], "domain": t["domain"],
         "embedding": table_emb.get(t["name"], [])}
        for t in tables
    ]
    session.run(
        """
        UNWIND $rows AS row
        MERGE (t:Table {name: row.name})
        SET t.description = row.description,
            t.domain      = row.domain,
            t.embedding   = row.embedding,
            t.build_id    = $build_id
        WITH t, row
        MATCH (d:Domain {name: row.domain})
        MERGE (d)-[r:HAS_TABLE]->(t)
        SET r.build_id = $build_id
        """,
        rows=rows, build_id=build_id,
    )


def _upsert_columns(session, tables: list[dict], col_emb: dict, build_id: str) -> None:
    rows = []
    for table in tables:
        for col in table["columns"]:
            key = f"{table['name']}.{col['name']}"
            rows.append({
                "key": key,
                "name": col["name"],
                "table_name": table["name"],
                "domain": table["domain"],
                "description": col.get("description", ""),
                "data_type": col["type"],
                "is_primary_key": col.get("primary_key", False),
                "aliases": col.get("aliases", []),
                "allowed_values": col.get("allowed_values", []),
                "embedding": col_emb.get(key, []),
            })
    session.run(
        """
        UNWIND $rows AS row
        MERGE (c:Column {key: row.key})
        SET c.name           = row.name,
            c.table_name     = row.table_name,
            c.domain         = row.domain,
            c.description    = row.description,
            c.data_type      = row.data_type,
            c.is_primary_key = row.is_primary_key,
            c.aliases        = row.aliases,
            c.allowed_values = row.allowed_values,
            c.embedding      = row.embedding,
            c.build_id       = $build_id
        WITH c, row
        MATCH (t:Table {name: row.table_name})
        MERGE (t)-[r:HAS_COLUMN]->(c)
        SET r.build_id = $build_id
        """,
        rows=rows, build_id=build_id,
    )


def _upsert_metrics(session, metrics: list[dict], build_id: str) -> None:
    rows = [
        {"name": m["name"], "expression": m["expression"],
         "description": m.get("description", ""), "tables": m.get("tables", [])}
        for m in metrics
    ]
    session.run(
        """
        UNWIND $rows AS row
        MERGE (m:Metric {name: row.name})
        SET m.expression  = row.expression,
            m.description = row.description,
            m.tables      = row.tables,
            m.build_id    = $build_id
        """,
        rows=rows, build_id=build_id,
    )


# ── relationship upserts (valid-only) ───────────────────────────────────────────

def _upsert_foreign_keys(session, relationships: list[dict], build_id: str) -> None:
    rows = [
        {"fk_key": f"{r['from_table']}.{r['from_column']}",
         "pk_key": f"{r['to_table']}.{r['to_column']}"}
        for r in relationships
    ]
    session.run(
        """
        UNWIND $rows AS row
        MATCH (fk:Column {key: row.fk_key}), (pk:Column {key: row.pk_key})
        MERGE (fk)-[r:FOREIGN_KEY]->(pk)
        SET r.build_id = $build_id
        """,
        rows=rows, build_id=build_id,
    )


def _upsert_references(session, relationships: list[dict], build_id: str) -> None:
    """Table-to-table projection of the column FKs, carrying the join keys.
    Only valid relationships reach here, so the join keys always resolve."""
    rows = [
        {"from_table": r["from_table"], "to_table": r["to_table"],
         "from_column": r["from_column"], "to_column": r["to_column"]}
        for r in relationships
    ]
    session.run(
        """
        UNWIND $rows AS row
        MATCH (ft:Table {name: row.from_table}), (tt:Table {name: row.to_table})
        MERGE (ft)-[r:REFERENCES {from_column: row.from_column, to_column: row.to_column}]->(tt)
        SET r.build_id = $build_id
        """,
        rows=rows, build_id=build_id,
    )


# ── sweep (orphan-killer) ────────────────────────────────────────────────────────

def _sweep(session, build_id: str) -> None:
    """Delete everything this build didn't touch — orphans from a shrunk schema.
    Scoped to KG-owned labels/edges; :Meta is never swept. DETACH DELETE handles
    edges incident to removed nodes; the edge sweep handles edges between two
    survivors whose relationship (or REFERENCES join-key signature) was removed."""
    session.run(
        """
        MATCH (n)
        WHERE (n:Domain OR n:Table OR n:Column OR n:Metric)
          AND coalesce(n.build_id, '') <> $build_id
        DETACH DELETE n
        """,
        build_id=build_id,
    )
    session.run(
        """
        MATCH ()-[r:HAS_TABLE|HAS_COLUMN|FOREIGN_KEY|REFERENCES]->()
        WHERE coalesce(r.build_id, '') <> $build_id
        DELETE r
        """,
        build_id=build_id,
    )


# ── build stamp / KG-freshness anchor ────────────────────────────────────────────

def _upsert_meta(session, schema: dict, check: RelationshipCheck,
                 build_id: str, fingerprint: str) -> None:
    """Stamp the (:Meta {key:'kg'}) build anchor. Called LAST so a build that
    dies mid-way never leaves a fresh stamp on a partial graph. built_at is
    recorded but deliberately excluded from the fingerprint."""
    tables = get_all_tables(schema)
    session.run(
        """
        MERGE (m:Meta {key: 'kg'})
        SET m.schema_fingerprint          = $fingerprint,
            m.model                        = $model,
            m.built_at                     = $built_at,
            m.build_id                     = $build_id,
            m.domains                      = $domains,
            m.tables                       = $tables,
            m.columns                      = $columns,
            m.skipped_relationships        = $skipped_count,
            m.skipped_relationship_details = $skipped_details
        """,
        fingerprint=fingerprint,
        model=MODEL_NAME,
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        build_id=build_id,
        domains=len(get_domains(schema)),
        tables=len(tables),
        columns=sum(len(t["columns"]) for t in tables),
        skipped_count=len(check.skipped),
        skipped_details=list(check.skip_reasons),
    )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )
```

- [ ] **Step 4: Run the builder tests to verify they pass**

Run: `uv run pytest tests/text2sql/test_builder.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Wire the pipeline to log `BuildStats`**

In `src/pipeline.py`, replace the `build(...)` call site (currently ~L94-100):

```python
    logger.info("LOAD — embedding metadata + building the Neo4j knowledge graph")
    from src.knowledge_graph.builder import build
    stats = build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    logger.info(
        "KG built: %d tables, %d columns, %d FK edges, %d skipped",
        stats.tables, stats.columns, stats.fk_edges, len(stats.skipped),
    )
    for reason in stats.skipped:
        logger.warning("  skipped relationship: %s", reason)
```

- [ ] **Step 6: Add the freshness idempotency test**

Append to `tests/text2sql/test_freshness.py`:

```python
def test_broken_relationship_schema_still_fingerprints_deterministically():
    # A schema with an invalid relationship must still hash stably, so re-running
    # the same (broken) schema is idempotent and kg_fresh stays honest — the
    # skip count, not the fingerprint, is the correctness signal.
    broken = _schema()
    broken["domains"][0]["relationships"] = [
        {"from_table": "t", "from_column": "nope", "to_table": "t", "to_column": "c"}
    ]
    assert kg_fingerprint(broken, "m") == kg_fingerprint(broken, "m")
    assert is_kg_fresh(kg_fingerprint(broken, "m"), broken, "m") is True
```

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/text2sql/ -q`
Expected: PASS (all tests, including the rewritten builder + new validate + freshness).

- [ ] **Step 8: Commit**

```bash
git add src/knowledge_graph/builder.py tests/text2sql/test_builder.py src/pipeline.py tests/text2sql/test_freshness.py
git commit -m "feat(kg): never-dark, corruption-proof KG build

- skip invalid relationships (both FOREIGN_KEY and REFERENCES) instead of
  silently writing bogus join keys
- stamp every node/edge with a per-run build_id and sweep untouched orphans
  (removed tables/columns/relationships no longer linger in the graph)
- Meta stamped last so an interrupted build self-heals; driver.close in finally
- UNWIND-batch every upsert (was hundreds of per-row round-trips)
- build() returns BuildStats; pipeline logs it

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Surface skipped relationships on `/api/health`

**Files:**
- Modify: `src/api/main.py` (`_kg_probe` ~L56-86, `health` ~L89-105)
- Modify: `tests/text2sql/test_main.py` (add one test)

**Interfaces:**
- Consumes: `Meta.skipped_relationships` (written by Task 2's `_upsert_meta`).
- Produces: `_kg_probe(...)` return dict gains a `"skipped"` key; `/api/health` JSON gains `kg_skipped_relationships`.

- [ ] **Step 1: Write the failing test**

Append to `tests/text2sql/test_main.py`:

```python
def test_health_reports_skipped_relationship_count(monkeypatch):
    fp = kg_fingerprint(load_schema(), MODEL_NAME)
    monkeypatch.setattr(main, "_kg_probe",
                        lambda *a: {"connected": True, "fingerprint": fp,
                                    "built_at": None, "skipped": 2})
    body = TestClient(main.app).get("/api/health").json()

    assert body["kg_skipped_relationships"] == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/text2sql/test_main.py::test_health_reports_skipped_relationship_count -v`
Expected: FAIL — `KeyError: 'kg_skipped_relationships'`.

- [ ] **Step 3: Extend `_kg_probe` to read the skip count**

In `src/api/main.py`, in `_kg_probe`, update the Cypher and both return dicts. The query becomes:

```python
            rec = s.run(
                "MATCH (m:Meta {key: 'kg'}) "
                "RETURN m.schema_fingerprint AS fingerprint, m.built_at AS built_at, "
                "m.skipped_relationships AS skipped"
            ).single()
        return {
            "connected": True,
            "fingerprint": rec["fingerprint"] if rec else None,
            "built_at": rec["built_at"] if rec else None,
            "skipped": rec["skipped"] if rec else None,
        }
```

And add `"skipped": None` to the two not-connected return dicts (the `if not all([...])` guard and the `except Exception` branch):

```python
        return {"connected": False, "fingerprint": None, "built_at": None, "skipped": None}
```

- [ ] **Step 4: Surface it in `health()`**

In `src/api/main.py`, add one line to the `health()` return dict (read defensively so existing mocked probes keep working):

```python
        "kg_fresh": kg_fresh,
        "kg_skipped_relationships": probe.get("skipped"),
        "kg_built_at": probe["built_at"],
```

- [ ] **Step 5: Run the health tests to verify they pass**

Run: `uv run pytest tests/text2sql/test_main.py -v`
Expected: PASS — the new test plus the three existing health tests (they omit `"skipped"`, so `probe.get("skipped")` returns `None`, which they don't assert on).

- [ ] **Step 6: Commit**

```bash
git add src/api/main.py tests/text2sql/test_main.py
git commit -m "feat(api): report skipped-relationship count in /api/health

_kg_probe reads Meta.skipped_relationships; health() surfaces it as
kg_skipped_relationships so a schema with broken joins is visible, not silent.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

The builder tests run against a fake session — they verify *which* Cypher is dispatched, not its effect. So the anti-corruption guarantee is proven here, against a real Aura instance, by exercising the two failure modes this task exists to fix. Run after Task 3.

- [ ] `uv run pytest tests/text2sql/ -q` — full suite green.
- [ ] `uv run uvicorn src.api.main:app --port 8000` starts cleanly; `GET /` returns HTML.
- [ ] **Baseline build:** `uv run python -m src.knowledge_graph.builder`; then `GET /api/health` → `kg_fresh: true`, `kg_skipped_relationships: 0`.

- [ ] **Problem #2 — orphan sweep + freshness trap.** Temporarily rename a table in `schema.json` (e.g. `returns` → `returns_v2`) and rebuild. In Neo4j Browser, confirm the old node and its edges are actually gone (not just that a `DETACH DELETE` was logged):

  ```cypher
  MATCH (t:Table {name: 'returns'}) RETURN count(t) AS node;           // expect 0
  MATCH (:Table {name: 'returns'})-[r]-() RETURN count(r) AS edges;    // expect 0
  ```

  Then confirm `GET /api/health` still shows `kg_fresh: true` — proving green means *clean*, not green-over-orphans. **Revert `schema.json` and rebuild.**

- [ ] **Problem #1 — skip completeness.** Temporarily point one relationship at a non-existent column in `schema.json` (change a `from_column` to `nope`) and rebuild. Confirm the build logs `Skipping invalid relationship: ...` and `GET /api/health` shows `kg_skipped_relationships` ≥ 1. In Neo4j Browser, confirm no `REFERENCES` edge carries the bogus key:

  ```cypher
  MATCH ()-[r:REFERENCES {from_column: 'nope'}]->() RETURN count(r) AS bogus;   // expect 0
  ```

  **Revert `schema.json` and rebuild** to a clean graph.

---

## Self-Review

**Verification altitude:** the builder tests run against a fake session, so the ✅s below prove the correct Cypher is *dispatched* (and only valid relationships reach the write payloads), not its runtime effect on a live graph. The runtime behavior — orphans actually removed, no bogus edge materialized, `kg_fresh` green meaning *clean* — is proven by the concrete "Final verification" steps against real Aura. Don't mistake the fake-session tests for proof the corruption is fixed.

**1. Spec coverage.**
- Pre-build relationship validation → Task 1 (`check_relationships`) + Task 2 (build consumes `check.valid`). ✅
- Warn + skip, both edges → Task 2 (`_upsert_foreign_keys`/`_upsert_references` take `check.valid` only; `test_invalid_relationship_writes_no_fk_or_reference_edge`). ✅
- Loud + durable (log + Meta + health + BuildStats) → Task 2 (`logger.warning`, `_upsert_meta` skip fields, `BuildStats.skipped`, pipeline log) + Task 3 (health). ✅
- Never-dark + orphan sweep → Task 2 (`MERGE` never deletes-first; `_sweep`). ✅
- Self-heal / Meta-last → Task 2 (`_run_build` order; `test_meta_is_stamped_last`, `test_sweep_runs_after_upserts_and_before_meta`). ✅
- `build_id` is a nonce, injectable → Task 2 (`build(..., build_id=None)`; tests inject `"BID"`). ✅
- UNWIND batching → Task 2 (one `session.run` per type). ✅
- `try/finally` driver close → Task 2 (`build`). ✅
- Freshness ⊥ validity → Task 2 (`_upsert_meta` stamps raw-schema fingerprint alongside skip count; `test_meta_is_stamped_last_with_skip_summary`; `test_broken_relationship_schema_still_fingerprints_deterministically`). ✅
- Health skip count → Task 3. ✅
- Non-goals (CLI hygiene beyond logger/try-finally, planner split, retries, atomic-snapshot txn) → not implemented. ✅

**2. Placeholder scan.** No TBD/TODO; every code step is complete and copy-pasteable. ✅

**3. Type consistency.** `check_relationships -> RelationshipCheck` (`.valid`, `.skipped`, `.skip_reasons`) used identically in Task 2. `build_id: str` threaded through every helper. `_run_build(session, schema, check, embeddings, build_id)` signature matches its call in `build()` and in `test_builder._run`. `_kg_probe` return keys (`connected/fingerprint/built_at/skipped`) match `health()`'s reads. ✅
