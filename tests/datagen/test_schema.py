"""Tests for sales catalog builder."""

from __future__ import annotations

import numpy as np
import pytest

from src.datagen.schema import SalesCatalog, build_catalog
from src.sales_data.domain.models import Product
from src.sales_data.metadata.enums import ProductCategory


class _CfgStub:
    n_customers = 50
    n_products_per_category = 4
    seed = 7


def test_build_catalog_customer_count():
    rng = np.random.default_rng(7)
    cat = build_catalog(_CfgStub(), rng)
    assert len(cat.customers) == 50


def test_build_catalog_products_per_category():
    rng = np.random.default_rng(7)
    cat = build_catalog(_CfgStub(), rng)
    assert set(cat.products_by_category) == {c.value for c in ProductCategory}
    for cat_name, products in cat.products_by_category.items():
        assert len(products) == 4
        for p in products:
            assert isinstance(p, Product)
            assert p.category == cat_name


def test_build_catalog_customer_ids_unique():
    rng = np.random.default_rng(7)
    cat = build_catalog(_CfgStub(), rng)
    ids = [c.customer_id for c in cat.customers]
    assert len(set(ids)) == len(ids)


def test_build_catalog_product_ids_unique_across_categories():
    rng = np.random.default_rng(7)
    cat = build_catalog(_CfgStub(), rng)
    all_ids = [p.product_id for products in cat.products_by_category.values() for p in products]
    assert len(set(all_ids)) == len(all_ids)


def test_build_catalog_customer_ids_zero_padded():
    rng = np.random.default_rng(7)
    cat = build_catalog(_CfgStub(), rng)
    assert cat.customers[0].customer_id == "CUST-0000"
    assert cat.customers[-1].customer_id == "CUST-0049"


def test_build_catalog_deterministic_same_seed():
    rng_a = np.random.default_rng(7)
    rng_b = np.random.default_rng(7)
    a = build_catalog(_CfgStub(), rng_a)
    b = build_catalog(_CfgStub(), rng_b)
    assert [c.customer_name for c in a.customers] == [c.customer_name for c in b.customers]


def test_build_catalog_too_many_products_per_category_raises():
    class Big:
        n_customers = 5
        n_products_per_category = 99
        seed = 7
    rng = np.random.default_rng(7)
    with pytest.raises(ValueError, match="product bank"):
        build_catalog(Big(), rng)


def test_sales_catalog_is_dataclass():
    cat = SalesCatalog(customers=[], products_by_category={})
    assert isinstance(cat.customers, list)
