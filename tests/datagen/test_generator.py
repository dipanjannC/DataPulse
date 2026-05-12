"""Tests for synthetic order generator."""

from __future__ import annotations

from collections import Counter
from datetime import date

import numpy as np

from src.datagen.generator import generate_orders
from src.datagen.schema import build_catalog
from src.sales_data.metadata.enums import Channel, ProductCategory, Region


class _Cfg:
    row_count = 200
    seed = 11
    n_customers = 30
    n_products_per_category = 5
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


def _build_and_generate(seed: int):
    cfg = _Cfg()
    cfg.seed = seed
    rng = np.random.default_rng(seed)
    catalog = build_catalog(cfg, rng)
    orders = generate_orders(catalog, cfg, rng)
    return cfg, catalog, orders


def test_row_count_exact():
    _, _, orders = _build_and_generate(11)
    assert len(orders) == 200


def test_order_ids_unique_and_padded():
    _, _, orders = _build_and_generate(11)
    ids = [o.order_id for o in orders]
    assert len(set(ids)) == len(ids)
    assert orders[0].order_id == "ORD-000000"
    assert orders[-1].order_id == "ORD-000199"


def test_determinism_same_seed():
    _, _, a = _build_and_generate(11)
    _, _, b = _build_and_generate(11)
    assert [(o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price, o.order_date, o.region, o.channel) for o in a] == \
           [(o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price, o.order_date, o.region, o.channel) for o in b]


def test_different_seeds_differ():
    _, _, a = _build_and_generate(11)
    _, _, b = _build_and_generate(12)
    assert a != b


def test_categorical_values_in_enums():
    _, _, orders = _build_and_generate(11)
    regions = {r.value for r in Region}
    channels = {c.value for c in Channel}
    for o in orders:
        assert o.region in regions
        assert o.channel in channels


def test_customer_id_present_in_catalog():
    _, catalog, orders = _build_and_generate(11)
    cust_ids = {c.customer_id for c in catalog.customers}
    for o in orders:
        assert o.customer_id in cust_ids


def test_product_id_present_in_catalog():
    _, catalog, orders = _build_and_generate(11)
    prod_ids = {p.product_id for ps in catalog.products_by_category.values() for p in ps}
    for o in orders:
        assert o.product_id in prod_ids


def test_price_within_band():
    cfg, catalog, orders = _build_and_generate(11)
    prod_cat = {p.product_id: c for c, ps in catalog.products_by_category.items() for p in ps}
    for o in orders:
        lo, hi = cfg.price_bands[prod_cat[o.product_id]]
        assert lo <= o.unit_price <= hi


def test_quantity_within_range():
    cfg, catalog, orders = _build_and_generate(11)
    prod_cat = {p.product_id: c for c, ps in catalog.products_by_category.items() for p in ps}
    for o in orders:
        qmin, qmax, _ = cfg.quantity_params[prod_cat[o.product_id]]
        assert qmin <= o.quantity <= qmax


def test_dates_within_range():
    _, _, orders = _build_and_generate(11)
    for o in orders:
        assert _Cfg.date_start <= o.order_date <= _Cfg.date_end


def test_weights_observed_roughly():
    cfg = _Cfg()
    cfg.row_count = 5000
    cfg.region_weights = {"North America": 80, "Europe": 10, "Asia Pacific": 10}
    rng = np.random.default_rng(11)
    cat = build_catalog(cfg, rng)
    orders = generate_orders(cat, cfg, rng)
    counts = Counter(o.region for o in orders)
    assert counts["North America"] > counts["Europe"] * 4
    assert counts["North America"] > counts["Asia Pacific"] * 4
