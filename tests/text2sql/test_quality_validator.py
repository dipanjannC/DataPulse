"""Schema-driven validator: conformance pass + each failure kind + RI detection.

Driven by tiny in-memory schema dicts and crafted DataFrames — no real DB,
network, or CSVs on disk.
"""

from __future__ import annotations

import pandas as pd

from src.quality.validator import validate_frames


def _schema() -> dict:
    return {
        "version": "test",
        "metrics": [],
        "domains": [
            {
                "name": "Test",
                "description": "test domain",
                "tables": [
                    {
                        "name": "parents",
                        "description": "parent rows",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
                            {"name": "name", "type": "TEXT", "primary_key": False, "nullable": False},
                        ],
                    },
                    {
                        "name": "children",
                        "description": "child rows",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
                            {"name": "parent_id", "type": "INTEGER", "primary_key": False, "nullable": True,
                             "foreign_key": {"table": "parents", "column": "id"}},
                            {"name": "amount", "type": "REAL", "primary_key": False, "nullable": False},
                        ],
                    },
                ],
                "relationships": [
                    {"from_table": "children", "from_column": "parent_id",
                     "to_table": "parents", "to_column": "id"},
                ],
            }
        ],
    }


def _clean_frames() -> dict[str, pd.DataFrame]:
    return {
        "parents": pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}),
        # parent_id has a NULL -> pandas reads it as float64; a legitimate nullable FK
        "children": pd.DataFrame({
            "id": [1, 2, 3],
            "parent_id": [1.0, 2.0, None],
            "amount": [10.5, 20.0, 0.0],
        }),
    }


def _kinds(report) -> set[str]:
    return {v.kind for v in report.schema.violations}


def test_clean_dataset_passes():
    report = validate_frames(_clean_frames(), _schema())

    assert report.schema.passed is True
    assert report.summary["pass"] is True
    assert report.summary["schema_pass"] is True
    assert report.summary["referential_integrity_pass"] is True
    assert report.distributions == {}  # chi-square deliberately skipped


def test_nullable_integer_read_as_float_is_not_a_dtype_violation():
    # The make-or-break adaptation: a nullable INTEGER column arrives as float64
    # (1.0, 2.0, NaN) and must NOT be flagged as a dtype violation.
    report = validate_frames(_clean_frames(), _schema())
    assert "dtype" not in _kinds(report)


def test_missing_column_detected():
    frames = _clean_frames()
    frames["children"] = frames["children"].drop(columns=["amount"])

    report = validate_frames(frames, _schema())
    assert any(v.kind == "missing_column" and v.field == "children.amount"
               for v in report.schema.violations)


def test_missing_table_detected_without_double_flagging_ri():
    frames = _clean_frames()
    del frames["parents"]

    report = validate_frames(frames, _schema())
    kinds = _kinds(report)
    assert "missing_table" in kinds
    # RI must not also fire when the parent table is absent
    assert "referential_integrity" not in kinds


def test_dtype_violation_detected():
    frames = _clean_frames()
    frames["children"]["amount"] = ["x", "y", "z"]  # REAL column with text

    report = validate_frames(frames, _schema())
    assert any(v.kind == "dtype" and v.field == "children.amount"
               for v in report.schema.violations)


def test_non_whole_float_in_integer_column_is_a_dtype_violation():
    frames = _clean_frames()
    frames["children"]["parent_id"] = [1.5, 2.5, 3.5]  # INTEGER column, non-whole

    report = validate_frames(frames, _schema())
    assert any(v.kind == "dtype" and v.field == "children.parent_id"
               for v in report.schema.violations)


def test_null_in_non_nullable_column_detected():
    frames = _clean_frames()
    frames["parents"] = pd.DataFrame({"id": [1, 2, 3], "name": ["a", None, "c"]})

    report = validate_frames(frames, _schema())
    assert any(v.kind == "null" and v.field == "parents.name"
               for v in report.schema.violations)


def test_duplicate_primary_key_detected():
    frames = _clean_frames()
    frames["parents"] = pd.DataFrame({"id": [1, 1, 2], "name": ["a", "b", "c"]})

    report = validate_frames(frames, _schema())
    assert any(v.kind == "duplicate" and v.field == "parents.id"
               for v in report.schema.violations)


def test_referential_integrity_orphan_detected():
    frames = _clean_frames()
    # parent_id 99 has no matching parents.id
    frames["children"]["parent_id"] = [1.0, 99.0, None]

    report = validate_frames(frames, _schema())
    ri = [v for v in report.schema.violations if v.kind == "referential_integrity"]
    assert len(ri) == 1
    assert ri[0].field == "children.parent_id -> parents.id"
    assert "99" in ri[0].detail
    assert report.summary["referential_integrity_pass"] is False


def test_self_referential_fk_resolves_within_the_same_table():
    schema = {
        "version": "test",
        "domains": [{
            "name": "Test", "description": "d",
            "tables": [{
                "name": "categories", "description": "c",
                "columns": [
                    {"name": "category_id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "parent_category_id", "type": "INTEGER", "primary_key": False, "nullable": True,
                     "foreign_key": {"table": "categories", "column": "category_id"}},
                ],
            }],
            "relationships": [
                {"from_table": "categories", "from_column": "parent_category_id",
                 "to_table": "categories", "to_column": "category_id"},
            ],
        }],
    }
    frames = {"categories": pd.DataFrame({
        "category_id": [1, 2, 3],
        "parent_category_id": [None, 1.0, 1.0],  # top-level NULL + valid self-refs
    })}

    report = validate_frames(frames, schema)
    assert report.schema.passed is True


# ── value-domain conformance (declared allowed_values) ──────────────────────────

def _vocab_schema() -> dict:
    return {
        "version": "test",
        "domains": [{
            "name": "Test", "description": "d",
            "tables": [{
                "name": "orders", "description": "o",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "status", "type": "TEXT", "primary_key": False, "nullable": False,
                     "allowed_values": ["Open", "Closed"]},
                ],
            }],
        }],
    }


def test_value_domain_violation_flagged_and_is_structural():
    frames = {"orders": pd.DataFrame({"id": [1, 2, 3], "status": ["Open", "Closed", "Bogus"]})}
    report = validate_frames(frames, _vocab_schema())

    vd = [v for v in report.schema.violations if v.kind == "value_domain"]
    assert len(vd) == 1
    assert vd[0].field == "orders.status"
    assert "Bogus" in vd[0].detail
    # value_domain counts as structural -> schema_pass reflects it
    assert report.summary["schema_pass"] is False


def test_value_domain_clean_dataset_passes():
    frames = {"orders": pd.DataFrame({"id": [1, 2, 3], "status": ["Open", "Closed", "Open"]})}
    report = validate_frames(frames, _vocab_schema())
    assert not any(v.kind == "value_domain" for v in report.schema.violations)


def test_value_domain_ignores_nulls():
    schema = _vocab_schema()
    schema["domains"][0]["tables"][0]["columns"][1]["nullable"] = True
    frames = {"orders": pd.DataFrame({"id": [1, 2, 3], "status": ["Open", None, "Closed"]})}
    report = validate_frames(frames, schema)
    assert not any(v.kind == "value_domain" for v in report.schema.violations)
