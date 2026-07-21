"""Tests for the embedding-text builders.

Only the pure `_*_text` helpers are exercised — they define what actually gets
vectorised at each granularity. The `build_*_embeddings` functions instantiate
the sentence-transformer model (a download) and are left to the live pipeline.
"""
from __future__ import annotations

from text2sql.embeddings.embed import _column_text, _domain_text, _table_text


def test_column_text():
    col = {"name": "loyalty_tier", "description": "Customer loyalty tier."}
    assert _column_text("customers", col) == "customers.loyalty_tier: Customer loyalty tier."


def test_table_text_includes_domain_for_routing_context():
    table = {"name": "orders", "domain": "Sales", "description": "Order headers."}
    assert _table_text(table) == "Sales • orders: Order headers."


def test_domain_text():
    domain = {"name": "Security", "description": "Cybersecurity operations."}
    assert _domain_text(domain) == "Security: Cybersecurity operations."
