"""KG builder: allowed_values is written onto Column nodes.

Drives _upsert_table_and_column_nodes against a fake session that captures the
Cypher parameters — no live Neo4j. Mirrors the aliases handling: a declared
vocabulary is passed through; a column without one defaults to [].
"""

from __future__ import annotations

from src.embeddings.embed import MODEL_NAME
from src.knowledge_graph.builder import _upsert_meta, _upsert_table_and_column_nodes
from src.knowledge_graph.freshness import kg_fingerprint


class _FakeSession:
    """Records every session.run(query, **params) call. Executes nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query, **params):
        self.calls.append((query, params))
        return None


def _tables() -> list[dict]:
    return [{
        "name": "orders",
        "domain": "Sales",
        "description": "order headers",
        "columns": [
            {"name": "order_id", "type": "INTEGER", "description": "id", "primary_key": True},
            {"name": "status", "type": "TEXT", "description": "order status",
             "allowed_values": ["Pending", "Shipped"]},
        ],
    }]


def _column_params(session: _FakeSession) -> dict[str, dict]:
    # column upserts are the ones carrying a `key`; keyed by that column key
    return {p["key"]: p for _, p in session.calls if "key" in p}


def test_allowed_values_passed_as_cypher_param():
    session = _FakeSession()
    _upsert_table_and_column_nodes(session, _tables(), table_emb={}, col_emb={})

    params = _column_params(session)
    assert params["orders.status"]["allowed_values"] == ["Pending", "Shipped"]


def test_column_without_vocabulary_defaults_to_empty_list():
    session = _FakeSession()
    _upsert_table_and_column_nodes(session, _tables(), table_emb={}, col_emb={})

    params = _column_params(session)
    assert params["orders.order_id"]["allowed_values"] == []


def test_allowed_values_set_in_the_column_merge_query():
    session = _FakeSession()
    _upsert_table_and_column_nodes(session, _tables(), table_emb={}, col_emb={})

    status_query = next(q for q, p in session.calls if p.get("key") == "orders.status")
    assert "c.allowed_values = $allowed_values" in status_query


# ── build stamp / KG-freshness anchor ───────────────────────────────────────────

def _meta_schema() -> dict:
    return {"version": "1", "domains": [{
        "name": "D", "description": "d",
        "tables": [{"name": "t", "description": "x",
                    "columns": [{"name": "c", "type": "TEXT"}]}],
    }]}


def test_meta_node_stamped_with_schema_fingerprint():
    schema = _meta_schema()
    session = _FakeSession()
    _upsert_meta(session, schema)

    assert len(session.calls) == 1
    query, params = session.calls[0]
    assert "MERGE (m:Meta {key: 'kg'})" in query
    assert params["fingerprint"] == kg_fingerprint(schema, MODEL_NAME)
    assert params["model"] == MODEL_NAME
    assert params["built_at"].endswith("Z")  # recorded, but not part of the fingerprint
    assert (params["domains"], params["tables"], params["columns"]) == (1, 1, 1)


def test_meta_fingerprint_is_deterministic_across_builds():
    schema = _meta_schema()
    a, b = _FakeSession(), _FakeSession()
    _upsert_meta(a, schema)
    _upsert_meta(b, schema)
    assert a.calls[0][1]["fingerprint"] == b.calls[0][1]["fingerprint"]
