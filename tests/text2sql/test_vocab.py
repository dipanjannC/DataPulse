"""vocab.values_for: the single sourcing point the generators draw from.

The invariant that keeps generate(seed) byte-identical is that values_for
returns schema.json order (== each generation site's historical order); these
tests pin that contract.
"""

from __future__ import annotations

import pytest

from src.datagen.vocab import VOCAB, values_for
from src.metadata.utils import get_categorical_values, load_schema


def test_vocab_is_exactly_the_schema_categorical_values():
    assert VOCAB == get_categorical_values(load_schema())


def test_values_for_returns_schema_order():
    # order is load-bearing: it equals the generator literal so weighted draws align
    assert values_for("orders", "status") == ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]
    assert values_for("servers", "status") == ["Running", "Stopped", "Maintenance", "Decommissioned"]


def test_values_for_returns_a_fresh_copy():
    got = values_for("orders", "status")
    got.append("X")
    assert values_for("orders", "status") == ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        values_for("orders", "nonexistent")
