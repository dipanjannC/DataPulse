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
(:Table)-[:REFERENCES {from_column, to_column, cardinality, build_id}]->(:Table)

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
            d.build_id = $build_id
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
            t.build_id = $build_id
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
            c.build_id = $build_id
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
            m.build_id = $build_id
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
    """Table-to-table projection of the column FKs, carrying the join keys and
    the join cardinality (an edge attribute, not part of the edge's identity) so
    the retriever can warn about fan-out. Only valid relationships reach here, so
    the join keys always resolve."""
    rows = [
        {"from_table": r["from_table"], "to_table": r["to_table"],
         "from_column": r["from_column"], "to_column": r["to_column"],
         "cardinality": r.get("cardinality")}
        for r in relationships
    ]
    session.run(
        """
        UNWIND $rows AS row
        MATCH (ft:Table {name: row.from_table}), (tt:Table {name: row.to_table})
        MERGE (ft)-[r:REFERENCES {from_column: row.from_column, to_column: row.to_column}]->(tt)
        SET r.cardinality = row.cardinality,
            r.build_id = $build_id
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
