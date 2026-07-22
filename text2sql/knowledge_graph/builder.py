"""Step 5 — Neo4j Knowledge Graph builder.

Node model
----------
(:Domain {name, description, embedding})
(:Table  {name, description, domain, embedding})
(:Column {key, name, table_name, domain, description, data_type, is_primary_key, aliases, embedding})
(:Metric {name, expression, description, tables})   # canonical business measures

Relationship model
------------------
(:Domain)-[:HAS_TABLE]->(:Table)
(:Table)-[:HAS_COLUMN]->(:Column)
(:Column)-[:FOREIGN_KEY]->(:Column)
(:Table)-[:REFERENCES {from_column, to_column}]->(:Table)

REFERENCES is the table-to-table projection of the column FKs; it carries the
exact join keys so the retriever can walk shortest join paths between tables
and hand the LLM explicit JOIN conditions.
"""
from __future__ import annotations

import os

from neo4j import GraphDatabase

from text2sql.embeddings.embed import (
    build_column_embeddings,
    build_domain_embeddings,
    build_table_embeddings,
)
from text2sql.metadata.utils import (
    get_all_relationships,
    get_all_tables,
    get_domains,
    get_metrics,
    load_schema,
)

VECTOR_DIM = 384   # all-MiniLM-L6-v2


def build(uri: str, user: str, password: str) -> None:
    schema      = load_schema()
    col_emb     = build_column_embeddings(schema)
    table_emb   = build_table_embeddings(schema)
    domain_emb  = build_domain_embeddings(schema)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as s:
        _create_constraints(s)
        _create_vector_indexes(s)
        _upsert_domain_nodes(s, get_domains(schema), domain_emb)
        _upsert_table_and_column_nodes(s, get_all_tables(schema), table_emb, col_emb)
        _upsert_fk_relationships(s, get_all_relationships(schema))
        _upsert_table_references(s, get_all_relationships(schema))
        _upsert_metric_nodes(s, get_metrics(schema))
    driver.close()

    tables     = get_all_tables(schema)
    col_count  = sum(len(t["columns"]) for t in tables)
    rel_count  = len(get_all_relationships(schema))
    print(
        f"Knowledge Graph built: {len(get_domains(schema))} domains | "
        f"{len(tables)} tables | {col_count} columns | {rel_count} FK edges | "
        f"{len(get_metrics(schema))} metrics"
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


# ── node upserts ──────────────────────────────────────────────────────────────

def _upsert_domain_nodes(session, domains: list[dict], domain_emb: dict) -> None:
    for d in domains:
        session.run(
            "MERGE (d:Domain {name: $name}) SET d.description = $desc, d.embedding = $emb",
            name=d["name"], desc=d["description"], emb=domain_emb.get(d["name"], []),
        )


def _upsert_table_and_column_nodes(
    session, tables: list[dict], table_emb: dict, col_emb: dict
) -> None:
    for table in tables:
        domain = table["domain"]

        # Table node
        session.run(
            """
            MERGE (t:Table {name: $name})
            SET t.description = $desc, t.domain = $domain, t.embedding = $emb
            WITH t
            MATCH (d:Domain {name: $domain})
            MERGE (d)-[:HAS_TABLE]->(t)
            """,
            name=table["name"], desc=table["description"], domain=domain,
            emb=table_emb.get(table["name"], []),
        )

        # Column nodes + HAS_COLUMN edge
        for col in table["columns"]:
            key = f"{table['name']}.{col['name']}"
            session.run(
                """
                MERGE (c:Column {key: $key})
                SET c.name           = $name,
                    c.table_name     = $table_name,
                    c.domain         = $domain,
                    c.description    = $desc,
                    c.data_type      = $dtype,
                    c.is_primary_key = $pk,
                    c.aliases        = $aliases,
                    c.embedding      = $emb
                WITH c
                MATCH (t:Table {name: $table_name})
                MERGE (t)-[:HAS_COLUMN]->(c)
                """,
                key=key,
                name=col["name"],
                table_name=table["name"],
                domain=domain,
                desc=col["description"],
                dtype=col["type"],
                pk=col.get("primary_key", False),
                aliases=col.get("aliases", []),
                emb=col_emb.get(key, []),
            )


def _upsert_fk_relationships(session, relationships: list[dict]) -> None:
    for rel in relationships:
        fk_key = f"{rel['from_table']}.{rel['from_column']}"
        pk_key = f"{rel['to_table']}.{rel['to_column']}"
        session.run(
            """
            MATCH (fk:Column {key: $fk_key}), (pk:Column {key: $pk_key})
            MERGE (fk)-[:FOREIGN_KEY]->(pk)
            """,
            fk_key=fk_key,
            pk_key=pk_key,
        )


def _upsert_table_references(session, relationships: list[dict]) -> None:
    """Table-to-table projection of the column FKs, carrying the join keys."""
    for rel in relationships:
        session.run(
            """
            MATCH (ft:Table {name: $from_table}), (tt:Table {name: $to_table})
            MERGE (ft)-[r:REFERENCES {from_column: $from_col, to_column: $to_col}]->(tt)
            """,
            from_table=rel["from_table"],
            to_table=rel["to_table"],
            from_col=rel["from_column"],
            to_col=rel["to_column"],
        )


def _upsert_metric_nodes(session, metrics: list[dict]) -> None:
    """Canonical business measures — the semantic layer that disambiguates which
    column is 'revenue', 'salary', etc. Surfaced to the LLM at generation time."""
    for m in metrics:
        session.run(
            """
            MERGE (m:Metric {name: $name})
            SET m.expression  = $expression,
                m.description = $description,
                m.tables      = $tables
            """,
            name=m["name"],
            expression=m["expression"],
            description=m.get("description", ""),
            tables=m.get("tables", []),
        )


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )
