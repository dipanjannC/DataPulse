"""Tests for synthetic CSV writer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import numpy as np

from src.datagen.generator import generate_orders
from src.datagen.schema import build_catalog
from src.datagen.writer import write_csv
from src.sales_data.metadata.column_definitions import EXPECTED_COLUMNS
from src.sales_data.metadata.enums import Channel, ProductCategory, Region


class _Cfg:
    row_count = 50
    seed = 3
    n_customers = 20
    n_products_per_category = 4
    date_start = date(2024, 1, 1)
    date_end = date(2024, 3, 31)
    region_weights = {r.value: 1 for r in Region}
    channel_weights = {c.value: 1 for c in Channel}
    category_weights = {c.value: 1 for c in ProductCategory}
    price_bands = {
        ProductCategory.ELECTRONICS.value: (15.0, 500.0),
        ProductCategory.STATIONERY.value: (1.5, 25.0),
        ProductCategory.FURNITURE.value: (30.0, 800.0),
    }
    quantity_params = {
        ProductCategory.ELECTRONICS.value: (1, 5, 1.6),
        ProductCategory.STATIONERY.value: (1, 20, 6.0),
        ProductCategory.FURNITURE.value: (1, 3, 1.2),
    }


def _build(tmp_path: Path):
    cfg = _Cfg()
    rng = np.random.default_rng(3)
    catalog = build_catalog(cfg, rng)
    orders = generate_orders(catalog, cfg, rng)
    out = tmp_path / "sales.csv"
    written = write_csv(orders, catalog, out)
    return written, orders, catalog


def test_write_csv_column_order(tmp_path: Path):
    written, _, _ = _build(tmp_path)
    df = pd.read_csv(written)
    assert list(df.columns) == EXPECTED_COLUMNS


def test_write_csv_row_count(tmp_path: Path):
    written, orders, _ = _build(tmp_path)
    df = pd.read_csv(written)
    assert len(df) == len(orders)


def test_write_csv_joins_customer_and_product(tmp_path: Path):
    written, _, catalog = _build(tmp_path)
    df = pd.read_csv(written)
    cust = {c.customer_id: c.customer_name for c in catalog.customers}
    prod = {p.product_id: (p.product_name, c) for c, ps in catalog.products_by_category.items() for p in ps}
    for _, row in df.iterrows():
        assert row["customer_name"] == cust[row["customer_id"]]
        pname, pcat = prod[row["product_id"]]
        assert row["product_name"] == pname
        assert row["category"] == pcat


def test_write_csv_creates_parent_dir(tmp_path: Path):
    cfg = _Cfg()
    rng = np.random.default_rng(3)
    catalog = build_catalog(cfg, rng)
    orders = generate_orders(catalog, cfg, rng)
    out = tmp_path / "nested" / "deep" / "sales.csv"
    write_csv(orders, catalog, out)
    assert out.exists()


def test_write_csv_date_format(tmp_path: Path):
    written, _, _ = _build(tmp_path)
    df = pd.read_csv(written)
    assert df["order_date"].iloc[0].count("-") == 2
    pd.to_datetime(df["order_date"])
