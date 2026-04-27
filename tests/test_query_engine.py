"""Tests for the query_engine bounded context."""

from src.query_engine.domain.query import Query, QueryResult


def test_query_creation():
    q = Query(query_type="neighbors", parameters={"node_id": "CUST-001"})
    assert q.query_type == "neighbors"
    assert q.parameters["node_id"] == "CUST-001"


def test_query_result_defaults():
    result = QueryResult()
    assert result.data is None
    assert result.metadata == {}
