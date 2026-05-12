"""Builds Customer and Product catalogs for synthetic generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
from faker import Faker

from src.sales_data.domain.models import Customer, Product
from src.sales_data.metadata.enums import ProductCategory


_PRODUCT_BANK: dict[str, list[str]] = {
    ProductCategory.ELECTRONICS.value: [
        "Wireless Mouse", "Mechanical Keyboard", "USB-C Hub", "Bluetooth Headphones",
        "Webcam 1080p", "Portable SSD", "Laptop Stand", "HDMI Cable",
        "Smart Plug", "Wireless Charger",
    ],
    ProductCategory.STATIONERY.value: [
        "Notebook A5", "Ballpoint Pen Pack", "Highlighter Set", "Sticky Notes",
        "Document Folder", "Whiteboard Marker", "Stapler", "Paper Clips Box",
        "Index Cards", "Desk Calendar",
    ],
    ProductCategory.FURNITURE.value: [
        "Standing Desk Mat", "Monitor Arm", "Ergonomic Chair", "Bookshelf",
        "Filing Cabinet", "Desk Lamp", "Office Desk", "Side Table",
        "Storage Bin", "Cable Tray",
    ],
}

_CATEGORY_PREFIX: dict[str, str] = {
    ProductCategory.ELECTRONICS.value: "ELE",
    ProductCategory.STATIONERY.value: "STA",
    ProductCategory.FURNITURE.value: "FUR",
}


class _CatalogConfig(Protocol):
    n_customers: int
    n_products_per_category: int
    seed: int


@dataclass(frozen=True)
class SalesCatalog:
    customers: list[Customer]
    products_by_category: dict[str, list[Product]] = field(default_factory=dict)


def _faker_from_rng(rng: np.random.Generator) -> Faker:
    seed = int(rng.integers(0, 2**31 - 1))
    faker = Faker()
    faker.seed_instance(seed)
    return faker


def build_catalog(config: _CatalogConfig, rng: np.random.Generator) -> SalesCatalog:
    faker = _faker_from_rng(rng)
    customers = [
        Customer(customer_id=f"CUST-{i:04d}", customer_name=faker.name())
        for i in range(config.n_customers)
    ]

    products_by_category: dict[str, list[Product]] = {}
    for category in ProductCategory:
        bank = _PRODUCT_BANK[category.value]
        if config.n_products_per_category > len(bank):
            raise ValueError(
                f"product bank for {category.value} has {len(bank)} names; "
                f"requested {config.n_products_per_category}"
            )
        prefix = _CATEGORY_PREFIX[category.value]
        products = [
            Product(
                product_id=f"PROD-{prefix}-{i:03d}",
                product_name=bank[i],
                category=category.value,
            )
            for i in range(config.n_products_per_category)
        ]
        products_by_category[category.value] = products

    return SalesCatalog(customers=customers, products_by_category=products_by_category)
