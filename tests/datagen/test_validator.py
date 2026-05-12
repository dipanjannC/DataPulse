"""Tests for synthetic CSV validator."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.datagen.config import Tolerances
from src.datagen.generator import generate_orders
from src.datagen.schema import build_catalog
from src.datagen.validator import validate
from src.datagen.writer import write_csv


class _Cfg:
    row_count = 2000
    seed = 5
    n_customers = 50
    n_products_per_category = 5
    date_start = date(2024, 1, 1)
    date_end = date(2024, 12, 31)
    region_weights = {"North America": 50, "Europe": 30, "Asia Pacific": 20}
    channel_weights = {"Online": 60, "Retail": 30, "Distributor": 10}
    category_weights = {"Electronics": 50, "Stationery": 30, "Furniture": 20}
    price_bands = {
        "Electronics": (15.0, 500.0),
        "Stationery": (1.5, 25.0),
        "Furniture": (30.0, 800.0),
    }
    quantity_params = {
        "Electronics": (1, 5, 1.6),
        "Stationery": (1, 20, 6.0),
        "Furniture": (1, 3, 1.2),
    }
    tolerances = Tolerances()


def _generate(tmp_path: Path, cfg: _Cfg) -> Path:
    rng = np.random.default_rng(cfg.seed)
    catalog = build_catalog(cfg, rng)
    orders = generate_orders(catalog, cfg, rng)
    return write_csv(orders, catalog, tmp_path / "sales.csv")


def test_clean_csv_passes(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    report = validate(path, cfg)
    assert report.schema.passed
    assert all(c.passed for c in report.distributions.values())
    assert report.summary["pass"]


def test_extra_column_fails_schema(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df["bogus"] = "x"
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.schema.passed
    assert any(v.kind == "extra_column" for v in report.schema.violations)


def test_missing_column_fails_schema(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path).drop(columns=["channel"])
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.schema.passed
    assert any(v.kind == "missing_column" for v in report.schema.violations)


def test_duplicate_order_id_fails_schema(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df.loc[0, "order_id"] = df.loc[1, "order_id"]
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.schema.passed
    assert any(v.kind == "duplicate" and v.field == "order_id" for v in report.schema.violations)


def test_skewed_region_fails_distribution(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df["region"] = "North America"
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.distributions["region"].passed
    assert report.distributions["region"].p_value is not None
    assert report.distributions["region"].p_value < 0.01


def test_price_band_violation_caught(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df.loc[df["category"] == "Electronics", "unit_price"] = 1000000.0
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.distributions["price_bands"].passed
    assert report.distributions["price_bands"].extra["violation_rate"] > 0.02


def test_date_out_of_range_caught(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df.loc[0, "order_date"] = "2099-01-01"
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.distributions["date_range"].passed


def test_quantity_out_of_range_caught(tmp_path: Path):
    cfg = _Cfg()
    path = _generate(tmp_path, cfg)
    df = pd.read_csv(path)
    df.loc[df["category"] == "Furniture", "quantity"] = 999
    df.to_csv(path, index=False)
    report = validate(path, cfg)
    assert not report.distributions["quantity"].passed
