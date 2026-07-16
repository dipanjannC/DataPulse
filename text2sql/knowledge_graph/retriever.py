"""Step 6 — KG retriever.

Given a natural-language question:
1. Embed the question.
2. Vector-search Column nodes (cosine similarity).
3. Expand to all columns of the matched tables.
4. Follow FOREIGN_KEY edges to pull in join-partner tables automatically.

Returns a schema context dict including domain information.
"""
from __future__ import annotations

from neo4j import GraphDatabase

from text2sql.embeddings.embed import embed_query

DEFAULT_TOP_K = 10


def retrieve_schema_context(
    question: str,
    uri: str,
    user: str,
    password: str,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """
    Return {
        'tables': {
            table_name: {
                'description': str,
                'domain': str,
                'columns': [{'name', 'type', 'description', 'is_pk'}, ...]
            }
        }
    }
    """
    q_vec  = embed_query(question)
    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as s:
        # Step A — vector search on Column embeddings
        hits = s.run(
            """
            CALL db.index.vector.queryNodes('column_embedding', $top_k, $q_vec)
            YIELD node AS col, score
            RETURN col.table_name AS table_name, score
            """,
            top_k=top_k,
            q_vec=q_vec,
        ).data()

        primary_tables = list({r["table_name"] for r in hits})

        # Step B — expand: all columns for primary tables + FK-linked tables
        rows = s.run(
            """
            MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
            WHERE t.name IN $tables
            OPTIONAL MATCH (c)-[:FOREIGN_KEY]->(pk:Column)
            RETURN t.name        AS table_name,
                   t.description AS table_desc,
                   t.domain      AS domain,
                   c.name        AS col_name,
                   c.description AS col_desc,
                   c.data_type   AS dtype,
                   c.is_primary_key AS is_pk,
                   pk.table_name AS fk_target_table
            """,
            tables=primary_tables,
        ).data()

        # Step C — also pull FK-target tables for JOIN hints
        linked_tables = {r["fk_target_table"] for r in rows if r.get("fk_target_table")}
        extra_tables  = list(linked_tables - set(primary_tables))

        extra_rows: list[dict] = []
        if extra_tables:
            extra_rows = s.run(
                """
                MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                WHERE t.name IN $tables
                RETURN t.name        AS table_name,
                       t.description AS table_desc,
                       t.domain      AS domain,
                       c.name        AS col_name,
                       c.description AS col_desc,
                       c.data_type   AS dtype,
                       c.is_primary_key AS is_pk,
                       null          AS fk_target_table
                """,
                tables=extra_tables,
            ).data()

    driver.close()
    return _build_context(rows + extra_rows)


def _build_context(rows: list[dict]) -> dict:
    tables: dict[str, dict] = {}
    for r in rows:
        tname = r["table_name"]
        if tname not in tables:
            tables[tname] = {
                "description": r.get("table_desc") or "",
                "domain":      r.get("domain") or "",
                "columns":     [],
            }
        tables[tname]["columns"].append({
            "name":        r["col_name"],
            "type":        r["dtype"],
            "description": r["col_desc"],
            "is_pk":       bool(r.get("is_pk")),
        })
    return {"tables": tables}
