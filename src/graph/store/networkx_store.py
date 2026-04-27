"""NetworkX-backed graph store."""

from __future__ import annotations

from typing import Any

import networkx as nx

from src.graph.domain.schema import EdgeType, NodeType


class NetworkXStore:
    """In-memory graph store using NetworkX."""

    def __init__(self) -> None:
        self.graph: nx.Graph = nx.Graph()

    def add_node(self, node_id: str, node_type: NodeType, **attrs: Any) -> None:
        """Add a node to the graph."""
        raise NotImplementedError

    def add_edge(self, source: str, target: str, edge_type: EdgeType, **attrs: Any) -> None:
        """Add an edge to the graph."""
        raise NotImplementedError

    def get_neighbors(self, node_id: str) -> list[str]:
        """Return neighbor node IDs."""
        raise NotImplementedError
