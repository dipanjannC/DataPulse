"""Tests for the agent's schema-formatting helper.

Only `_format_schema` is exercised here (it is pure). The other tools in
`text2sql.agent.tools` touch SQLite / the KG and are covered via the agent tests.
"""
from __future__ import annotations

from text2sql.agent.tools import _format_schema


def _ctx() -> dict:
    return {
        "tables": {
            "orders": {
                "description": "order headers", "domain": "Sales",
                "columns": [
                    {"name": "order_id", "type": "INTEGER", "description": "id", "is_pk": True},
                    {"name": "customer_id", "type": "INTEGER", "description": "fk", "is_pk": False},
                ],
            },
            "customers": {
                "description": "customer master", "domain": "Sales",
                "columns": [
                    {"name": "customer_id", "type": "INTEGER", "description": "id", "is_pk": True},
                    {"name": "loyalty_tier", "type": "TEXT", "description": "tier", "is_pk": False,
                     "allowed_values": ["Bronze", "Silver", "Gold", "Platinum"]},
                ],
            },
        },
        "joins": [
            {"from_table": "orders", "from_column": "customer_id",
             "to_table": "customers", "to_column": "customer_id"},
        ],
        "domains": [{"name": "Sales", "score": 0.9}],
        "metrics": [
            {"name": "total revenue", "expression": "SUM(order_items.line_total)",
             "description": "canonical transactional revenue"},
        ],
    }


def test_format_schema_emits_domain_grouping_and_join_paths():
    out = _format_schema(_ctx())

    assert "### Domain: Sales" in out
    assert "#### orders" in out and "#### customers" in out
    # PK flag renders
    assert "| order_id | INTEGER | Yes | id |" in out
    # the discovered join key is handed to the LLM explicitly
    assert "## Join Paths" in out
    assert "orders.customer_id = customers.customer_id" in out
    # canonical metric definition disambiguates which column is 'revenue'
    assert "## Metric definitions" in out
    assert "total revenue: SUM(order_items.line_total)" in out


def test_format_schema_backward_compatible_without_joins_or_domain():
    """Old-shape context (no 'joins' key, tables lacking 'domain') must not crash
    and must not emit a Join Paths section."""
    ctx = {
        "tables": {
            "products": {
                "description": "catalog",
                "columns": [{"name": "product_id", "type": "INTEGER", "description": "id", "is_pk": True}],
            },
        },
    }
    out = _format_schema(ctx)

    assert "#### products" in out
    assert "## Join Paths" not in out
    assert "### Domain:" not in out
    assert "## Metric definitions" not in out


def test_format_schema_renders_allowed_values_inline():
    """A column's declared vocabulary is surfaced on its row so the agent can
    filter categoricals without a sample_values round-trip."""
    out = _format_schema(_ctx())
    assert "tier (one of: Bronze, Silver, Gold, Platinum)" in out
    # a column without a vocabulary is not annotated
    assert "| order_id | INTEGER | Yes | id |" in out


def test_format_schema_adds_cross_domain_note_for_islands():
    """Two domains with no bridging join -> an explicit 'cannot be joined' note
    steers the model off a hallucinated cross-domain join."""
    ctx = {
        "tables": {
            "customers": {"description": "c", "domain": "Sales",
                          "columns": [{"name": "customer_id", "type": "INTEGER", "description": "id", "is_pk": True}]},
            "sec_users": {"description": "u", "domain": "Security",
                          "columns": [{"name": "user_id", "type": "INTEGER", "description": "id", "is_pk": True}]},
        },
        "joins": [],
    }
    out = _format_schema(ctx)
    assert "## Cross-domain note" in out
    assert "cannot be joined" in out


def test_format_schema_no_cross_domain_note_within_one_domain():
    # _ctx() is entirely Sales tables joined on customer_id -> no note
    assert "## Cross-domain note" not in _format_schema(_ctx())


def test_format_schema_renders_fanout_warning_when_cardinality_present():
    ctx = _ctx()
    ctx["joins"][0]["cardinality"] = "many-to-one"
    out = _format_schema(ctx)
    assert "orders.customer_id = customers.customer_id" in out
    assert "fans out" in out and "COUNT(DISTINCT)" in out


def test_format_schema_join_line_is_plain_without_cardinality():
    # backward-compat: a not-yet-rebuilt graph returns no cardinality -> plain line
    out = _format_schema(_ctx())
    assert "orders.customer_id = customers.customer_id" in out
    assert "fans out" not in out
