"""Tests for the graph bounded context."""

from src.graph.domain.schema import EdgeType, NodeType


def test_node_types_exist():
    assert NodeType.CUSTOMER.value == "customer"
    assert NodeType.ORDER.value == "order"
    assert NodeType.PRODUCT.value == "product"


def test_edge_types_exist():
    assert EdgeType.PLACED.value == "placed"
    assert EdgeType.CONTAINS.value == "contains"
