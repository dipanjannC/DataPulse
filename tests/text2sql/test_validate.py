"""check_relationships: schema-internal consistency of schema.json relationships."""

from __future__ import annotations

from src.metadata.validate import check_relationships


def _schema(relationships: list[dict]) -> dict:
    return {
        "version": "1",
        "domains": [{
            "name": "Sales", "description": "d",
            "tables": [
                {"name": "orders", "description": "", "columns": [
                    {"name": "order_id", "type": "INTEGER", "primary_key": True},
                    {"name": "customer_id", "type": "INTEGER"},
                ]},
                {"name": "customers", "description": "", "columns": [
                    {"name": "customer_id", "type": "INTEGER", "primary_key": True},
                ]},
                {"name": "employees", "description": "", "columns": [
                    {"name": "employee_id", "type": "INTEGER", "primary_key": True},
                    {"name": "manager_id", "type": "INTEGER"},
                ]},
            ],
            "relationships": relationships,
        }],
    }


_VALID = {"from_table": "orders", "from_column": "customer_id",
          "to_table": "customers", "to_column": "customer_id"}


def test_valid_relationship_is_kept():
    check = check_relationships(_schema([_VALID]))
    assert check.valid == [_VALID]
    assert check.skipped == []


def test_bad_from_column_is_skipped_with_reason_naming_the_column():
    bad = {**_VALID, "from_column": "custommer_id"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert len(check.skipped) == 1
    assert "orders.custommer_id" in check.skipped[0].reason
    assert "from_column" in check.skipped[0].reason


def test_bad_to_table_is_skipped_with_reason_naming_the_table():
    bad = {**_VALID, "to_table": "custmers"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert "custmers" in check.skipped[0].reason
    assert "to_table" in check.skipped[0].reason


def test_endpoint_in_data_but_not_declared_in_schema_is_skipped():
    # 'notes' is not a declared column on orders -> the exact gap the quality
    # validator misses today (it only checks CSV-vs-schema).
    bad = {**_VALID, "from_column": "notes"}
    check = check_relationships(_schema([bad]))
    assert check.valid == []
    assert "orders.notes" in check.skipped[0].reason


def test_self_referential_relationship_is_valid():
    self_ref = {"from_table": "employees", "from_column": "manager_id",
                "to_table": "employees", "to_column": "employee_id"}
    check = check_relationships(_schema([self_ref]))
    assert check.valid == [self_ref]
    assert check.skipped == []


def test_skip_reasons_property_lists_all_reasons():
    bad1 = {**_VALID, "from_column": "nope"}
    bad2 = {**_VALID, "to_table": "nope"}
    check = check_relationships(_schema([_VALID, bad1, bad2]))
    assert len(check.valid) == 1
    assert len(check.skip_reasons) == 2


def test_relationship_broken_on_both_endpoints_reports_both():
    # both endpoints reference undeclared columns -> the reason names BOTH,
    # not just the first (no more first-error-wins).
    bad = {"from_table": "orders", "from_column": "nope_a",
           "to_table": "customers", "to_column": "nope_b"}
    reason = check_relationships(_schema([bad])).skipped[0].reason
    assert "orders.nope_a" in reason
    assert "customers.nope_b" in reason


def test_missing_endpoint_key_reads_as_missing_not_none():
    # a relationship dict that omits an endpoint key must not render as 'None'.
    bad = {"from_table": "orders", "from_column": "customer_id", "to_table": "customers"}
    reason = check_relationships(_schema([bad])).skipped[0].reason
    assert "None" not in reason
    assert "to_column" in reason and "missing" in reason
