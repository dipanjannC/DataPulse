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
