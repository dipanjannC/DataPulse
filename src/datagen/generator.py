"""Generates synthetic Order rows from a SalesCatalog."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

import numpy as np

from src.datagen.schema import SalesCatalog
from src.sales_data.domain.models import Order
from src.sales_data.metadata.enums import Channel, ProductCategory, Region


class _GenConfig(Protocol):
    row_count: int
    date_start: date
    date_end: date
    region_weights: dict[str, float]
    channel_weights: dict[str, float]
    category_weights: dict[str, float]
    price_bands: dict[str, tuple[float, float]]
    quantity_params: dict[str, tuple[int, int, float]]


def _normalize(weights: dict[str, float], keys: list[str]) -> np.ndarray:
    raw = np.array([float(weights.get(k, 0.0)) for k in keys], dtype=float)
    total = raw.sum()
    if total <= 0:
        raise ValueError(f"weights must sum to > 0; got {raw}")
    return raw / total


def generate_orders(
    catalog: SalesCatalog,
    config: _GenConfig,
    rng: np.random.Generator,
) -> list[Order]:
    region_keys = [r.value for r in Region]
    channel_keys = [c.value for c in Channel]
    category_keys = [c.value for c in ProductCategory]

    region_p = _normalize(config.region_weights, region_keys)
    channel_p = _normalize(config.channel_weights, channel_keys)
    category_p = _normalize(config.category_weights, category_keys)

    customers = catalog.customers
    products_by_cat = catalog.products_by_category

    n_days = (config.date_end - config.date_start).days + 1
    orders: list[Order] = []
    for i in range(config.row_count):
        category = str(rng.choice(category_keys, p=category_p))
        region = str(rng.choice(region_keys, p=region_p))
        channel = str(rng.choice(channel_keys, p=channel_p))

        products = products_by_cat[category]
        product = products[int(rng.integers(0, len(products)))]
        customer = customers[int(rng.integers(0, len(customers)))]

        qmin, qmax, qmean = config.quantity_params[category]
        qty_raw = int(rng.poisson(qmean))
        qty = max(qmin, min(qmax, qty_raw))

        lo, hi = config.price_bands[category]
        price = round(float(rng.uniform(lo, hi)), 2)

        day_offset = int(rng.integers(0, n_days))
        order_date = config.date_start + timedelta(days=day_offset)

        orders.append(
            Order(
                order_id=f"ORD-{i:06d}",
                customer_id=customer.customer_id,
                product_id=product.product_id,
                quantity=qty,
                unit_price=price,
                order_date=order_date,
                region=region,
                channel=channel,
            )
        )
    return orders
