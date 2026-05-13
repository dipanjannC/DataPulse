"""Tests for Neo4jGraphBuilder using a fake store that records Cypher."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.graph.builder.neo4j_graph_builder import Neo4jGraphBuilder
from src.graph.domain.schema import EdgeType, NodeType
from src.sales_data.metadata.column_definitions import EXPECTED_COLUMNS


class _FakeStore:
    def __init__(self, read_responses: dict[str, list[dict]] | None = None):
        self.constraints_setup_count = 0
        self.writes: list[tuple[str, dict]] = []
        self.reads: list[tuple[str, dict]] = []
        self._read_responses = read_responses or {}

    def setup_constraints(self) -> list[str]:
        self.constraints_setup_count += 1
        return []

    def run_write(self, query: str, **params) -> list[dict]:
        self.writes.append((query, params))
        return []

    def run_read(self, query: str, **params) -> list[dict]:
        self.reads.append((query, params))
        for needle, rows in self._read_responses.items():
            if needle in query:
                return rows
        return []


def _sample_csv(tmp_path: Path, rows: int = 5) -> Path:
    out = tmp_path / "sales.csv"
    df = pd.DataFrame(
        {
            "order_id": [f"ORD-{i:06d}" for i in range(rows)],
            "customer_id": [f"CUST-{i:04d}" for i in range(rows)],
            "customer_name": [f"Customer {i}" for i in range(rows)],
            "product_id": [f"PROD-ELE-{i:03d}" for i in range(rows)],
            "product_name": [f"Widget {i}" for i in range(rows)],
            "category": ["Electronics"] * rows,
            "quantity": [1] * rows,
            "unit_price": [9.99] * rows,
            "order_date": ["2024-01-15"] * rows,
            "region": ["North America"] * rows,
            "channel": ["Online"] * rows,
        }
    )
    df.to_csv(out, index=False, columns=EXPECTED_COLUMNS)
    return out


def test_build_from_csv_calls_setup_constraints(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    builder.build_from_csv(_sample_csv(tmp_path))
    assert store.constraints_setup_count == 1


def test_build_from_csv_returns_row_count(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store, batch_size=2)
    stats = builder.build_from_csv(_sample_csv(tmp_path, rows=5))
    assert stats.rows == 5
    assert stats.batches == 3


def test_merge_query_covers_all_node_labels(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    builder.build_from_csv(_sample_csv(tmp_path, rows=1))
    assert len(store.writes) == 1
    query, params = store.writes[0]
    for node in NodeType:
        assert f":{node.value}" in query, f"missing MERGE for label {node.value}"


def test_merge_query_covers_all_edge_types(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    builder.build_from_csv(_sample_csv(tmp_path, rows=1))
    query, _ = store.writes[0]
    for edge in EdgeType:
        assert f":{edge.value}]" in query, f"missing MERGE for edge {edge.value}"


def test_merge_uses_unwind_for_batching(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store, batch_size=3)
    builder.build_from_csv(_sample_csv(tmp_path, rows=7))
    assert len(store.writes) == 3
    sizes = [len(params["rows"]) for _, params in store.writes]
    assert sizes == [3, 3, 1]
    for query, _ in store.writes:
        assert "UNWIND $rows AS row" in query


def test_merge_params_include_all_csv_columns(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    builder.build_from_csv(_sample_csv(tmp_path, rows=1))
    _, params = store.writes[0]
    row = params["rows"][0]
    for col in EXPECTED_COLUMNS:
        assert col in row, f"missing column {col} in batch payload"


def test_count_nodes_queries_every_label():
    store = _FakeStore(read_responses={f":{n.value}": [{"c": 1}] for n in NodeType})
    builder = Neo4jGraphBuilder(store)
    counts = builder.count_nodes()
    assert set(counts) == {n.value for n in NodeType}
    assert all(v == 1 for v in counts.values())
    assert len(store.reads) == 6


def test_idempotent_uses_merge_not_create(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    builder.build_from_csv(_sample_csv(tmp_path, rows=1))
    query, _ = store.writes[0]
    assert "MERGE" in query
    assert "CREATE (" not in query


def test_csv_not_found_raises(tmp_path):
    store = _FakeStore()
    builder = Neo4jGraphBuilder(store)
    with pytest.raises(FileNotFoundError):
        builder.build_from_csv(tmp_path / "nope.csv")
