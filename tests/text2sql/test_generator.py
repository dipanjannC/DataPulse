"""Tests for the SQL-generator prompt formatting.

Only `_format_schema` is exercised (pure). `generate_sql` calls the Groq API and
is intentionally left to the live acceptance check.
"""
from __future__ import annotations

from text2sql.sql_gen.generator import _format_schema, generate_sql


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
                    {"name": "loyalty_tier", "type": "TEXT", "description": "tier", "is_pk": False},
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


def test_generate_sql_short_circuits_on_empty_retrieval():
    """Empty KG retrieval returns a clean failure without touching Groq (this
    call would raise if it tried to reach the network with a bogus key)."""
    result = generate_sql("anything", {"tables": {}}, api_key="not-used")

    assert result["success"] is False
    assert result["attempts"] == 0
    assert "No relevant tables" in result["error"]
