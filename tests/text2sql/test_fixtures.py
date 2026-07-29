"""fixtures.load_fixture — the reference-table data seam.

End-to-end determinism (fixtures reproduce the tracked CSVs) is covered by
test_datagen_registry; here we pin the loader contract, including the two
placeholder tables the generators fill in place.
"""

from __future__ import annotations

import pytest

from src.datagen.fixtures import load_fixture

PURE = [("categories", 9), ("sla_definitions", 12), ("marketing_channels", 8), ("sec_roles", 6)]


@pytest.mark.parametrize("name,count", PURE)
def test_pure_fixtures_load_expected_rows(name, count):
    rows = load_fixture(name)
    assert isinstance(rows, list) and len(rows) == count
    assert all(isinstance(r, dict) for r in rows)


def test_regions_manager_name_is_a_placeholder():
    rows = load_fixture("regions")
    assert len(rows) == 5
    # manager_name is a null placeholder the generator fills with fake.name();
    # its key position (before timezone) fixes the CSV column order.
    for r in rows:
        assert r["manager_name"] is None
        assert list(r) == ["region_id", "region_name", "country", "manager_name", "timezone"]


def test_customer_segments_count_is_a_range_placeholder():
    rows = load_fixture("customer_segments")
    assert len(rows) == 10
    for r in rows:
        lo, hi = r["customer_count"]  # [lo, hi] the generator draws rng.randint from
        assert isinstance(lo, int) and isinstance(hi, int) and lo < hi


def test_load_fixture_returns_fresh_mutable_lists():
    a = load_fixture("categories")
    a[0]["category_name"] = "MUT"
    assert load_fixture("categories")[0]["category_name"] == "Electronics"
