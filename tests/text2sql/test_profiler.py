"""Descriptive profiler: per-role stats, null/cardinality accounting, and the
JSON-safety guarantee (no numpy scalars, no NaN). Driven by tiny in-memory
schema dicts + crafted DataFrames — no CSVs, DB, or network.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.quality.profiler import profile_frames


def _schema() -> dict:
    return {
        "version": "test",
        "domains": [{
            "name": "Test", "description": "d",
            "tables": [{
                "name": "orders", "description": "o",
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "customer_id", "type": "INTEGER", "primary_key": False, "nullable": True,
                     "foreign_key": {"table": "customers", "column": "id"}},
                    {"name": "amount", "type": "REAL", "primary_key": False, "nullable": False},
                    {"name": "status", "type": "TEXT", "primary_key": False, "nullable": False,
                     "allowed_values": ["Open", "Closed", "Cancelled"]},
                    {"name": "country", "type": "TEXT", "primary_key": False, "nullable": True},
                    {"name": "order_date", "type": "DATE", "primary_key": False, "nullable": False},
                ],
            }],
        }],
    }


def _frames() -> dict[str, pd.DataFrame]:
    return {"orders": pd.DataFrame({
        "id": [1, 2, 3, 4],
        "customer_id": [10.0, 10.0, 20.0, None],   # nullable FK -> float64 with a NULL
        "amount": [10.0, 20.0, 30.0, 40.0],
        "status": ["Open", "Open", "Closed", "Open"],  # "Cancelled" never appears
        "country": ["USA", "USA", "UK", "UK"],
        "order_date": ["2022-01-01", "2022-06-15", "2023-03-01", "2024-12-31"],
    })}


def _col(profile: dict, table: str, column: str) -> dict:
    return profile[table]["columns"][column]


def test_table_shape_and_row_count():
    p = profile_frames(_frames(), _schema())
    assert p["orders"]["row_count"] == 4
    assert p["orders"]["column_count"] == 6
    assert set(p["orders"]["columns"]) == {"id", "customer_id", "amount", "status", "country", "order_date"}


def test_roles_assigned_from_schema():
    p = profile_frames(_frames(), _schema())
    roles = {c: prof["role"] for c, prof in p["orders"]["columns"].items()}
    assert roles == {
        "id": "key",
        "customer_id": "reference",   # foreign_key wins over the INTEGER numeric default
        "amount": "numeric",
        "status": "categorical",      # declared allowed_values
        "country": "text",            # low-cardinality text still gets a frequency view (below)
        "order_date": "datetime",
    }


def test_numeric_stats_and_histogram():
    p = profile_frames(_frames(), _schema())
    amount = _col(p, "orders", "amount")
    assert amount["min"] == 10.0 and amount["max"] == 40.0
    assert amount["mean"] == 25.0
    assert amount["p50"] == 25.0
    hist = amount["histogram"]
    assert hist is not None
    assert sum(hist["counts"]) == 4                    # every non-null row is binned
    assert len(hist["edges"]) == len(hist["counts"]) + 1


def test_null_and_cardinality_accounting():
    p = profile_frames(_frames(), _schema())
    cust = _col(p, "orders", "customer_id")
    assert cust["count"] == 3 and cust["nulls"] == 1
    assert cust["null_pct"] == 25.0
    assert cust["distinct"] == 2                        # 10 and 20 (NULL excluded)


def test_categorical_top_and_unused_vocabulary():
    p = profile_frames(_frames(), _schema())
    status = _col(p, "orders", "status")
    counts = {d["value"]: d["count"] for d in status["top"]}
    assert counts == {"Open": 3, "Closed": 1}
    assert status["allowed"] == ["Open", "Closed", "Cancelled"]
    assert status["unused"] == ["Cancelled"]            # declared but never generated


def test_low_cardinality_text_gets_frequency_without_allowed():
    p = profile_frames(_frames(), _schema())
    country = _col(p, "orders", "country")
    assert country["role"] == "text"
    counts = {d["value"]: d["count"] for d in country["top"]}
    assert counts == {"USA": 2, "UK": 2}
    assert "allowed" not in country                     # no declared vocabulary


def test_datetime_range():
    p = profile_frames(_frames(), _schema())
    d = _col(p, "orders", "order_date")
    assert d["min"] == "2022-01-01" and d["max"] == "2024-12-31"


def test_all_null_numeric_yields_none_not_nan():
    schema = {
        "version": "t", "domains": [{
            "name": "T", "description": "d",
            "tables": [{"name": "t", "description": "t", "columns": [
                {"name": "x", "type": "REAL", "primary_key": False, "nullable": True},
            ]}],
        }],
    }
    frames = {"t": pd.DataFrame({"x": [np.nan, np.nan, np.nan]})}
    x = profile_frames(frames, schema)["t"]["columns"]["x"]
    assert x["mean"] is None and x["histogram"] is None
    assert x["null_pct"] == 100.0


def test_missing_table_profiles_as_empty():
    schema = _schema()
    p = profile_frames({}, schema)  # no frames at all
    assert p["orders"]["row_count"] == 0
    assert p["orders"]["columns"] == {}


def test_profile_is_json_serializable():
    # The make-or-break guarantee: numpy int64/float64 and NaN must be unwrapped,
    # or Starlette's JSON encoder rejects the /api/quality response.
    p = profile_frames(_frames(), _schema())
    dumped = json.dumps(p)                              # raises on numpy/NaN if we slipped
    assert json.loads(dumped) == p


# ── genericity: the profiler (and thus the panel) is dataset-agnostic ────────
# The visualizations must reproduce for ANY plugged-in dataset, not just the
# project's sales/IT/HR/marketing/security schema. This drives an entirely
# different, made-up multi-domain catalog (Healthcare + Logistics) through the
# SAME profiler and asserts every viz signal comes back — which also guards
# against anyone ever hardcoding real table/column names into the profiler.

def _alien_schema() -> dict:
    return {
        "version": "alien",
        "domains": [
            {"name": "Healthcare", "description": "h", "tables": [
                {"name": "patients", "description": "p", "columns": [
                    {"name": "patient_id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "blood_type", "type": "TEXT", "nullable": False,
                     "allowed_values": ["A+", "O+", "B+", "AB-"]},        # AB- declared, never generated
                    {"name": "age", "type": "INTEGER", "nullable": False},
                    {"name": "admission_date", "type": "DATE", "nullable": False},
                    {"name": "insurance_provider", "type": "TEXT", "nullable": True},   # has real nulls
                ]},
                {"name": "appointments", "description": "a", "columns": [
                    {"name": "appt_id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "patient_id", "type": "INTEGER", "nullable": False,
                     "foreign_key": {"table": "patients", "column": "patient_id"}},
                ]},
            ], "relationships": [
                {"from_table": "appointments", "from_column": "patient_id",
                 "to_table": "patients", "to_column": "patient_id"},
            ]},
            {"name": "Logistics", "description": "l", "tables": [
                {"name": "shipments", "description": "s", "columns": [
                    {"name": "shipment_id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "weight_kg", "type": "REAL", "nullable": False},
                    {"name": "carrier", "type": "TEXT", "nullable": False},    # low-card text, no allowed_values
                ]},
            ]},
        ],
    }


def _alien_frames() -> dict[str, pd.DataFrame]:
    return {
        "patients": pd.DataFrame({
            "patient_id": [1, 2, 3, 4, 5],
            "blood_type": ["A+", "A+", "O+", "B+", "O+"],               # AB- never appears
            "age": [5, 20, 41, 67, 88],
            "admission_date": ["2024-01-02", "2024-03-15", "2024-06-01", "2024-09-20", "2024-12-26"],
            "insurance_provider": ["Aetna", None, "Cigna", None, "Aetna"],   # 2/5 null
        }),
        "appointments": pd.DataFrame({"appt_id": [1, 2, 3], "patient_id": [1, 2, 2]}),
        "shipments": pd.DataFrame({
            "shipment_id": [1, 2, 3, 4],
            "weight_kg": [0.5, 12.0, 30.25, 49.9],
            "carrier": ["FedEx", "UPS", "FedEx", "DHL"],
        }),
    }


def test_profiles_an_entirely_different_catalog_verbatim():
    # The profile's tables/domains are exactly the alien schema's — never a
    # leaked or hardcoded table from the project's own schema.
    p = profile_frames(_alien_frames(), _alien_schema())
    assert set(p) == {"patients", "appointments", "shipments"}
    assert {t["domain"] for t in p.values()} == {"Healthcare", "Logistics"}
    assert p["patients"]["row_count"] == 5
    assert p["patients"]["columns"]["patient_id"]["role"] == "key"
    assert p["appointments"]["columns"]["patient_id"]["role"] == "reference"   # FK across alien tables
    assert p["shipments"]["columns"]["weight_kg"]["role"] == "numeric"


def test_alien_unused_vocabulary_detected():
    bt = profile_frames(_alien_frames(), _alien_schema())["patients"]["columns"]["blood_type"]
    assert bt["role"] == "categorical"
    assert bt["unused"] == ["AB-"]                       # declared vocabulary that never appears


def test_alien_partial_completeness_reported():
    # The null-aware meter path the project's all-non-null data never exercises.
    ins = profile_frames(_alien_frames(), _alien_schema())["patients"]["columns"]["insurance_provider"]
    assert ins["nulls"] == 2 and ins["null_pct"] == 40.0


def test_alien_numeric_histogram_and_datetime_range():
    p = profile_frames(_alien_frames(), _alien_schema())
    w = p["shipments"]["columns"]["weight_kg"]
    assert w["min"] == 0.5 and w["max"] == 49.9
    assert w["histogram"] is not None and sum(w["histogram"]["counts"]) == 4
    d = p["patients"]["columns"]["admission_date"]
    assert d["role"] == "datetime" and d["min"] == "2024-01-02" and d["max"] == "2024-12-26"


def test_alien_low_cardinality_text_gets_bars_without_allowed_values():
    carrier = profile_frames(_alien_frames(), _alien_schema())["shipments"]["columns"]["carrier"]
    assert carrier["role"] == "text"
    assert {d["value"]: d["count"] for d in carrier["top"]} == {"FedEx": 2, "UPS": 1, "DHL": 1}
    assert "allowed" not in carrier                       # no declared vocabulary → no unused set


def test_alien_profile_is_json_serializable():
    p = profile_frames(_alien_frames(), _alien_schema())
    assert json.loads(json.dumps(p)) == p
