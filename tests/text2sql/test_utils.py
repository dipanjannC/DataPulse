"""get_categorical_values: table.column -> allowed_values mapping.

Driven by a tiny in-memory schema plus one smoke check against the real
schema.json (the canonical vocabulary contract).
"""

from __future__ import annotations

from src.metadata.utils import get_categorical_values, load_schema


def _schema() -> dict:
    return {
        "version": "test",
        "domains": [
            {
                "name": "D",
                "description": "d",
                "tables": [
                    {
                        "name": "orders",
                        "description": "o",
                        "columns": [
                            {"name": "status", "type": "TEXT", "allowed_values": ["A", "B"]},
                            {"name": "amount", "type": "REAL"},  # no vocabulary
                        ],
                    },
                    {
                        "name": "customers",
                        "description": "c",
                        "columns": [
                            {"name": "tier", "type": "TEXT", "allowed_values": ["Gold"]},
                        ],
                    },
                ],
            }
        ],
    }


def test_maps_table_column_to_allowed_values():
    assert get_categorical_values(_schema()) == {
        "orders.status": ["A", "B"],
        "customers.tier": ["Gold"],
    }


def test_columns_without_allowed_values_are_absent():
    assert "orders.amount" not in get_categorical_values(_schema())


def test_returns_copies_not_schema_references():
    schema = _schema()
    cats = get_categorical_values(schema)
    cats["orders.status"].append("X")
    # mutating the accessor result must not corrupt the schema
    assert schema["domains"][0]["tables"][0]["columns"][0]["allowed_values"] == ["A", "B"]


def test_real_schema_orders_status_is_canonical():
    cats = get_categorical_values(load_schema())
    assert cats["orders.status"] == ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]
