"""Step 5 — Neo4j Knowledge Graph builder.

Node model
----------
(:Domain {name, description})
(:Table  {name, description, domain})
(:Column {key, name, table_name, domain, description, data_type, is_primary_key, embedding})

Relationship model
------------------
(:Domain)-[:HAS_TABLE]->(:Table)
(:Table)-[:HAS_COLUMN]->(:Column)
(:Column)-[:FOREIGN_KEY]->(:Column)
"""
from __future__ import annotations

import os

from neo4j import GraphDatabase

from text2sql.embeddings.embed import build_column_embeddings
from text2sql.metadata.utils import (
    get_all_relationships,
    get_all_tables,
    get_domains,
    load_schema,
)

VECTOR_DIM = 384   # all-MiniLM-L6-v2


def build(uri: str, user: str, password: str) -> None:
    schema     = load_schema()
    embeddings = build_column_embeddings(schema)

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as s:
        _create_constraints(s)
        _create_vector_index(s)
        _upsert_domain_nodes(s, get_domains(schema))
        _upsert_table_and_column_nodes(s, get_all_tables(schema), embeddings)
        _upsert_fk_relationships(s, get_all_relationships(schema))
    driver.close()

    tables     = get_all_tables(schema)
    col_count  = sum(len(t["columns"]) for t in tables)
    print(
        f"Knowledge Graph built: {len(get_domains(schema))} domains | "
        f"{len(tables)} tables | {col_count} columns"
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


def _create_vector_index(session) -> None:
    session.run(f"""
        CREATE VECTOR INDEX column_embedding IF NOT EXISTS
        FOR (c:Column) ON (c.embedding)
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {VECTOR_DIM},
                `vector.similarity_function`: 'cosine'
            }}
        }}
    """)


# ── node upserts ──────────────────────────────────────────────────────────────

def _upsert_domain_nodes(session, domains: list[dict]) -> None:
    for d in domains:
        session.run(
            "MERGE (d:Domain {name: $name}) SET d.description = $desc",
            name=d["name"], desc=d["description"],
        )


def _upsert_table_and_column_nodes(
    session, tables: list[dict], embeddings: dict
) -> None:
    for table in tables:
        domain = table["domain"]

        # Table node
        session.run(
            """
            MERGE (t:Table {name: $name})
            SET t.description = $desc, t.domain = $domain
            WITH t
            MATCH (d:Domain {name: $domain})
            MERGE (d)-[:HAS_TABLE]->(t)
            """,
            name=table["name"], desc=table["description"], domain=domain,
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
                emb=embeddings.get(key, []),
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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )
