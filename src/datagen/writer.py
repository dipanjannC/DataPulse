"""Writes synthetic Order rows to CSV, joining catalog metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.datagen.schema import SalesCatalog
from src.sales_data.domain.models import Order
from src.sales_data.metadata.column_definitions import EXPECTED_COLUMNS


def _rows(orders: Iterable[Order], catalog: SalesCatalog) -> list[dict[str, object]]:
    cust = {c.customer_id: c.customer_name for c in catalog.customers}
    prod: dict[str, tuple[str, str]] = {}
    for cat_name, products in catalog.products_by_category.items():
        for p in products:
            prod[p.product_id] = (p.product_name, cat_name)

    out: list[dict[str, object]] = []
    for o in orders:
        pname, pcat = prod[o.product_id]
        out.append({
            "order_id": o.order_id,
            "customer_id": o.customer_id,
            "customer_name": cust[o.customer_id],
            "product_id": o.product_id,
            "product_name": pname,
            "category": pcat,
            "quantity": int(o.quantity),
            "unit_price": float(o.unit_price),
            "order_date": o.order_date.isoformat(),
            "region": o.region,
            "channel": o.channel,
        })
    return out


def write_csv(orders: list[Order], catalog: SalesCatalog, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(_rows(orders, catalog), columns=EXPECTED_COLUMNS)
    df.to_csv(target, index=False)
    return target
