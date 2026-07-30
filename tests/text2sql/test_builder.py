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


def test_references_carry_cardinality_defaulting_to_none():
    # base schema's valid relationship declares no cardinality -> None (a rel
    # authored before cardinality existed must not crash the build)
    session = _FakeSession()
    _run(session, _schema())
    ref_q = next(q for q, p in session.calls if "REFERENCES" in q and "rows" in p)
    assert "r.cardinality = row.cardinality" in ref_q
    assert _rows_for(session, "REFERENCES")[0]["cardinality"] is None


def test_references_carry_declared_cardinality():
    session = _FakeSession()
    schema = _schema()
    schema["domains"][0]["relationships"][0]["cardinality"] = "many-to-one"
    _run(session, schema)
    assert _rows_for(session, "REFERENCES")[0]["cardinality"] == "many-to-one"
