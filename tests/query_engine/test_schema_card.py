"""Tests that the schema card stays in sync with the enums."""

from __future__ import annotations

from src.graph.domain.schema import EdgeType, NodeType
from src.query_engine.agent.schema_card import SCHEMA_CARD
from src.sales_data.metadata.enums import Channel, ProductCategory, Region


def test_card_lists_every_node_label():
    for node in NodeType:
        assert f"({node.value})" in SCHEMA_CARD


def test_card_lists_every_edge_type():
    for edge in EdgeType:
        assert f":{edge.value}]" in SCHEMA_CARD


def test_card_lists_enum_values():
    for region in Region:
        assert region.value in SCHEMA_CARD
    for channel in Channel:
        assert channel.value in SCHEMA_CARD
    for cat in ProductCategory:
        assert cat.value in SCHEMA_CARD


def test_card_says_read_only():
    assert "MATCH" in SCHEMA_CARD
    assert "rejected" in SCHEMA_CARD.lower()
