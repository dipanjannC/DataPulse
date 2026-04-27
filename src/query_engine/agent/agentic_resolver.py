"""LLM-driven agentic query resolver."""

from __future__ import annotations

from src.graph.store.networkx_store import NetworkXStore
from src.query_engine.domain.query import Query, QueryResult


class AgenticResolver:
    """Resolves natural-language queries using an LLM agent.

    Requires the ``langchain`` optional dependency.
    """

    def __init__(self, store: NetworkXStore) -> None:
        self.store = store

    def resolve(self, query: Query) -> QueryResult:
        """Plan and execute graph operations via LLM reasoning.

        Args:
            query: A Query with a natural-language question in parameters.

        Returns:
            QueryResult with synthesized answer.
        """
        raise NotImplementedError("AgenticResolver.resolve is not yet implemented.")
