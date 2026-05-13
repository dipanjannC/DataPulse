"""Tests for the run_cypher tool: guards, row cap, error wrapping."""

from __future__ import annotations

import pytest

from src.query_engine.agent.cypher_tool import MAX_ROWS, run_cypher


class _FakeStore:
    def __init__(self, rows=None, raise_exc=None):
        self.rows = rows or []
        self.calls: list[str] = []
        self.raise_exc = raise_exc

    def run_read(self, query: str, **_params):
        self.calls.append(query)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.rows


def test_read_only_match_passes():
    store = _FakeStore(rows=[{"n": 1}])
    out = run_cypher("MATCH (c:Customer) RETURN c LIMIT 5", store)
    assert "error" not in out
    assert out["rows"] == [{"n": 1}]
    assert out["row_count"] == 1
    assert out["truncated_at"] is None


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (n:Customer {customer_id: 'x'})",
        "MATCH (n) DELETE n",
        "MERGE (c:Customer {customer_id: 'x'})",
        "MATCH (n) SET n.x = 1",
        "DROP CONSTRAINT foo",
        "MATCH (n) REMOVE n.x",
        "MATCH (n) DETACH DELETE n",
        "LOAD CSV FROM 'file:///x.csv' AS row CREATE (n:X {a: row[0]})",
        "CALL apoc.create.node(['Customer'], {})",
        "CALL db.labels()",
        "CALL dbms.functions()",
    ],
)
def test_write_keywords_rejected(query):
    store = _FakeStore()
    out = run_cypher(query, store)
    assert "error" in out and out["error"], f"expected error for {query!r}"
    assert out["rows"] == []
    assert store.calls == []


def test_case_insensitive_guard():
    out = run_cypher("match (n) delete n", _FakeStore())
    assert "error" in out and "delete" in out["error"].lower()


def test_guard_ignores_comments():
    store = _FakeStore(rows=[{"a": 1}])
    out = run_cypher("// CREATE is mentioned in a comment\nMATCH (n) RETURN n", store)
    assert "error" not in out or not out.get("error")
    assert out["rows"] == [{"a": 1}]


def test_guard_ignores_block_comments():
    store = _FakeStore(rows=[{"a": 1}])
    out = run_cypher("/* DELETE */ MATCH (n) RETURN n", store)
    assert "error" not in out or not out.get("error")


def test_property_named_create_does_not_trip_guard():
    store = _FakeStore(rows=[])
    out = run_cypher("MATCH (n) RETURN n.create_date", store)
    assert "error" not in out or not out.get("error")


def test_empty_query_rejected():
    out = run_cypher("   ", _FakeStore())
    assert "error" in out and "empty" in out["error"].lower()


def test_non_string_query_rejected():
    out = run_cypher(None, _FakeStore())  # type: ignore[arg-type]
    assert "error" in out


def test_row_cap_applied():
    rows = [{"i": i} for i in range(MAX_ROWS + 50)]
    store = _FakeStore(rows=rows)
    out = run_cypher("MATCH (n) RETURN n", store)
    assert len(out["rows"]) == MAX_ROWS
    assert out["truncated_at"] == MAX_ROWS
    assert out["row_count"] == MAX_ROWS


def test_driver_error_wrapped():
    store = _FakeStore(raise_exc=RuntimeError("driver boom"))
    out = run_cypher("MATCH (n) RETURN n", store)
    assert "error" in out and "RuntimeError" in out["error"] and "boom" in out["error"]
    assert out["rows"] == []
