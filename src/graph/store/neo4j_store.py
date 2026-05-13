"""Thin wrapper around the official neo4j driver for DataPulse."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase, Session

from src.graph.domain.schema import NodeType


_UNIQUE_KEY_BY_LABEL: dict[str, str] = {
    NodeType.CUSTOMER.value: "customer_id",
    NodeType.ORDER.value: "order_id",
    NodeType.PRODUCT.value: "product_id",
    NodeType.REGION.value: "name",
    NodeType.CHANNEL.value: "name",
    NodeType.CATEGORY.value: "name",
}


class Neo4jStore:
    """Owns a driver, exposes sessions, and handles schema setup."""

    def __init__(self, uri: str, username: str, password: str, *, database: str | None = None) -> None:
        if not uri:
            raise ValueError("Neo4jStore: uri is required (set NEO4J_URI in .env)")
        self._uri = uri
        self._database = database
        self._driver: Driver = GraphDatabase.driver(uri, auth=(username, password))

    @classmethod
    def from_settings(cls, settings: Any) -> "Neo4jStore":
        return cls(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)

    @contextmanager
    def session(self) -> Iterator[Session]:
        kwargs: dict[str, Any] = {}
        if self._database:
            kwargs["database"] = self._database
        with self._driver.session(**kwargs) as session:
            yield session

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def setup_constraints(self) -> list[str]:
        statements = [
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            for label, key in _UNIQUE_KEY_BY_LABEL.items()
        ]
        with self.session() as session:
            for stmt in statements:
                session.run(stmt)
        return statements

    def run_read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def run_write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]
