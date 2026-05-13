"""Tests for Neo4jStore. Driver is mocked; no live Neo4j needed."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.graph.store.neo4j_store import Neo4jStore


class _FakeRecord(dict):
    """Mimics neo4j.Record's iteration as dict-like."""


@contextmanager
def _fake_session(captured: list[tuple[str, dict]], rows_for_run: list[_FakeRecord] | None = None):
    session = MagicMock()

    def _run(query: str, **params):
        captured.append((query, params))
        result = MagicMock()
        result.__iter__ = lambda self: iter(rows_for_run or [])
        return result

    session.run.side_effect = _run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    yield session


@pytest.fixture
def captured() -> list[tuple[str, dict]]:
    return []


@pytest.fixture
def store(captured: list[tuple[str, dict]]):
    with patch("src.graph.store.neo4j_store.GraphDatabase") as gd:
        driver = MagicMock()

        def _session(**_kw):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.run.side_effect = lambda q, **p: (captured.append((q, p)), _MockResult([])).__getitem__(1)
            return cm

        driver.session.side_effect = _session
        gd.driver.return_value = driver
        yield Neo4jStore("bolt://test", "neo4j", "pw")


class _MockResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


def test_init_requires_uri():
    with pytest.raises(ValueError, match="uri is required"):
        Neo4jStore("", "neo4j", "pw")


def test_from_settings_uses_settings_fields(captured):
    class S:
        neo4j_uri = "bolt://settings"
        neo4j_username = "alice"
        neo4j_password = "secret"

    with patch("src.graph.store.neo4j_store.GraphDatabase") as gd:
        Neo4jStore.from_settings(S())
        gd.driver.assert_called_once_with("bolt://settings", auth=("alice", "secret"))


def test_setup_constraints_issues_one_per_label(store, captured):
    statements = store.setup_constraints()
    assert len(statements) == 6
    issued = [q for q, _ in captured]
    assert len(issued) == 6
    for q in issued:
        assert q.startswith("CREATE CONSTRAINT IF NOT EXISTS FOR (n:")
        assert "IS UNIQUE" in q


def test_setup_constraints_covers_all_node_labels(store):
    statements = store.setup_constraints()
    joined = "\n".join(statements)
    for label in ("Customer", "Order", "Product", "Region", "Channel", "Category"):
        assert f"(n:{label})" in joined


def test_run_read_returns_list_of_dicts():
    with patch("src.graph.store.neo4j_store.GraphDatabase") as gd:
        rows = [_FakeRecord(a=1, b=2), _FakeRecord(a=3, b=4)]

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.run.return_value = _MockResult(rows)

        driver = MagicMock()
        driver.session.return_value = cm
        gd.driver.return_value = driver

        store = Neo4jStore("bolt://test", "neo4j", "pw")
        out = store.run_read("MATCH (n) RETURN n LIMIT 2")
        assert out == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_context_manager_closes_driver():
    with patch("src.graph.store.neo4j_store.GraphDatabase") as gd:
        driver = MagicMock()
        gd.driver.return_value = driver
        with Neo4jStore("bolt://test", "neo4j", "pw") as s:
            assert s is not None
        driver.close.assert_called_once()


def test_passes_database_when_provided():
    with patch("src.graph.store.neo4j_store.GraphDatabase") as gd:
        driver = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.run.return_value = _MockResult([])
        driver.session.return_value = cm
        gd.driver.return_value = driver
        store = Neo4jStore("bolt://test", "neo4j", "pw", database="neo4j")
        store.run_read("MATCH (n) RETURN n")
        driver.session.assert_called_with(database="neo4j")
