"""Tests for the graph bounded context."""

from src.graph.domain.schema import EdgeType, NodeType


def test_node_types_are_camelcase():
    assert NodeType.CUSTOMER.value == "Customer"
    assert NodeType.ORDER.value == "Order"
    assert NodeType.PRODUCT.value == "Product"
    assert NodeType.REGION.value == "Region"
    assert NodeType.CHANNEL.value == "Channel"
    assert NodeType.CATEGORY.value == "Category"


def test_edge_types_are_upper_snake():
    assert EdgeType.PLACED.value == "PLACED"
    assert EdgeType.CONTAINS.value == "CONTAINS"
    assert EdgeType.IN_REGION.value == "IN_REGION"
    assert EdgeType.VIA_CHANNEL.value == "VIA_CHANNEL"
    assert EdgeType.BELONGS_TO.value == "BELONGS_TO"
