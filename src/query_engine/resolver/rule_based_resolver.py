"""Simple graph-traversal query resolver."""

from __future__ import annotations

from src.graph.store.networkx_store import NetworkXStore
from src.query_engine.domain.query import Query, QueryResult


class SimpleResolver:
    """Resolves structured queries via direct graph traversal."""

    def __init__(self, store: NetworkXStore) -> None:
        self.store = store

    def resolve(self, query: Query) -> QueryResult:
        """Execute a structured query against the graph.

        Args:
            query: A Query object specifying type and parameters.

        Returns:
            QueryResult with matching data.
        """
        raise NotImplementedError("SimpleResolver.resolve is not yet implemented.")
