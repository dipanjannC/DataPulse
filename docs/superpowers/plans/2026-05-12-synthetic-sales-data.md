# Synthetic Sales Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, configurable synthetic sales-data pipeline (catalog → orders → CSV → quality report) targeting the existing sales domain models, replacing the broken KYC-origin scripts in `src/datagen/`.

**Architecture:** Four layers in `src/datagen/`: `config` (load JSON), `schema` (build customer/product catalogs), `generator` (sample orders), `writer` (emit CSV), `validator` (schema + distribution checks). Two CLI entry points (`generate`, `validate`). Pure deterministic — single `numpy.random.Generator` seeded from config.

**Tech Stack:** Python 3.10+, uv, pandas, numpy (transitively), Faker, scipy, pytest. Reuses `src/sales_data/domain/models.py` and `src/sales_data/metadata/{enums,column_definitions}.py`.

**Spec:** `docs/superpowers/specs/2026-05-12-synthetic-sales-data-design.md`

---

## File map

**Create:**
- `src/datagen/__init__.py`
- `src/datagen/config.py` — `SyntheticConfig` dataclass + `load_config(path)`
- `src/datagen/schema.py` — `SalesCatalog` + `build_catalog(config, rng)`
- `src/datagen/generator.py` — `OrderGenerator` + `generate_orders(catalog, config, rng)`
- `src/datagen/writer.py` — `write_csv(orders, path)`
- `src/datagen/reports.py` — `QualityReport`, `SchemaCheck`, `DistributionCheck` dataclasses + JSON helpers
- `src/datagen/validator.py` — `validate(csv_path, config)` returning `QualityReport`
- `src/datagen/generate.py` — CLI entry
- `src/datagen/validate.py` — CLI entry
- `tests/datagen/__init__.py`
- `tests/datagen/test_config.py`
- `tests/datagen/test_schema.py`
- `tests/datagen/test_generator.py`
- `tests/datagen/test_writer.py`
- `tests/datagen/test_validator.py`
- `tests/datagen/test_reports.py`

**Modify:**
- `data/sample/synthetic_config.sample.json` — replace KYC content with sales-flavored template
- `.claude/commands/datagen.md` — rewrite to call new entries
- `.claude/MEMORY.md` — mark datagen working for sales
- `pyproject.toml` — `faker`, `scipy` deps added via `uv add`

**Move (preserving git history via `git mv`):**
- All 9 existing `src/datagen/*.py` → `src/datagen/_kyc_legacy/` (no `__init__.py` in `_kyc_legacy/`)

---

## Task 0: Dependencies & directory move

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Move: `src/datagen/*.py` → `src/datagen/_kyc_legacy/`

- [ ] **Step 1: Add deps via uv**

Run:
```
uv add faker scipy
```
Expected: `pyproject.toml` gains `faker` and `scipy` under `[project] dependencies`, `uv.lock` updated.

- [ ] **Step 2: Move KYC scripts out of the way**

Run (PowerShell):
```
git mv src/datagen/create_synthetic_config.py src/datagen/_kyc_legacy/create_synthetic_config.py
git mv src/datagen/create_synthetic_data.py   src/datagen/_kyc_legacy/create_synthetic_data.py
git mv src/datagen/draft.py                   src/datagen/_kyc_legacy/draft.py
git mv src/datagen/generate_ddl.py            src/datagen/_kyc_legacy/generate_ddl.py
git mv src/datagen/generate_semantic_values.py src/datagen/_kyc_legacy/generate_semantic_values.py
git mv src/datagen/ingest_metadata.py         src/datagen/_kyc_legacy/ingest_metadata.py
git mv src/datagen/load_synthetic_to_db.py    src/datagen/_kyc_legacy/load_synthetic_to_db.py
git mv src/datagen/validate_metadata.py       src/datagen/_kyc_legacy/validate_metadata.py
git mv src/datagen/validate_synthetic_data.py src/datagen/_kyc_legacy/validate_synthetic_data.py
```
Expected: `src/datagen/_kyc_legacy/` contains 9 files; no `__init__.py` there.

- [ ] **Step 3: Create the new package marker**

Write `src/datagen/__init__.py`:
```python
"""Synthetic sales data generation and quality validation."""
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock src/datagen/
git commit -m "chore(datagen): archive KYC scripts, add faker/scipy"
```

---

## Task 1: SyntheticConfig + load_config (config.py)

**Files:**
- Create: `src/datagen/config.py`
- Test: `tests/datagen/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/__init__.py` (empty).

Create `tests/datagen/test_config.py`:
```python
"""Tests for synthetic config loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.datagen.config import (
    SyntheticConfig,
    Tolerances,
    load_config,
)


SAMPLE = {
    "row_count": 1000,
    "target": "data/raw/sales_1k.csv",
    "generation": {
        "seed": 42,
        "catalog": {"n_customers": 120, "n_products_per_category": 8},
        "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
    },
    "validation": {
        "enabled": True,
        "report_path": "data/raw/quality_report.json",
        "fail_on_error": False,
        "tolerances": {
            "distribution_chi2_p_min": 0.01,
            "band_violation_rate_max": 0.02,
        },
    },
    "controls": {
        "value_distributions": {
            "region": {"North America": 50, "Europe": 30, "Asia Pacific": 20},
            "channel": {"Online": 60, "Retail": 30, "Distributor": 10},
            "category": {"Electronics": 50, "Stationery": 30, "Furniture": 20},
        },
        "price_bands": {
            "Electronics": {"min": 15.0, "max": 500.0},
            "Stationery": {"min": 1.5, "max": 25.0},
            "Furniture": {"min": 30.0, "max": 800.0},
        },
        "quantity_distribution": {
            "Electronics": {"min": 1, "max": 5, "mean": 1.6},
            "Stationery": {"min": 1, "max": 20, "mean": 6.0},
            "Furniture": {"min": 1, "max": 3, "mean": 1.2},
        },
    },
}


def _write(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_load_config_parses_sample(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, SAMPLE))
    assert isinstance(cfg, SyntheticConfig)
    assert cfg.row_count == 1000
    assert cfg.target == Path("data/raw/sales_1k.csv")
    assert cfg.seed == 42
    assert cfg.n_customers == 120
    assert cfg.n_products_per_category == 8
    assert cfg.date_start.isoformat() == "2024-01-01"
    assert cfg.date_end.isoformat() == "2024-12-31"
    assert cfg.region_weights == {"North America": 50, "Europe": 30, "Asia Pacific": 20}
    assert cfg.price_bands["Electronics"] == (15.0, 500.0)
    assert cfg.quantity_params["Stationery"] == (1, 20, 6.0)


def test_load_config_default_tolerances(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(SAMPLE))
    payload["validation"].pop("tolerances")
    cfg = load_config(_write(tmp_path, payload))
    assert cfg.tolerances == Tolerances(
        distribution_chi2_p_min=0.01,
        band_violation_rate_max=0.02,
    )


def test_load_config_missing_required_raises(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(SAMPLE))
    payload.pop("row_count")
    with pytest.raises(KeyError, match="row_count"):
        load_config(_write(tmp_path, payload))


def test_load_config_invalid_date_range_raises(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(SAMPLE))
    payload["generation"]["date_range"]["end"] = "2023-12-31"
    with pytest.raises(ValueError, match="date_range"):
        load_config(_write(tmp_path, payload))


def test_load_config_unknown_region_weight_raises(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(SAMPLE))
    payload["controls"]["value_distributions"]["region"]["Antarctica"] = 5
    with pytest.raises(ValueError, match="region"):
        load_config(_write(tmp_path, payload))
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_config.py -v`
Expected: collection or import error (`src.datagen.config` does not yet exist).

- [ ] **Step 3: Implement config.py**

Create `src/datagen/config.py`:
```python
"""Synthetic data configuration loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from src.sales_data.metadata.enums import Channel, ProductCategory, Region


@dataclass(frozen=True)
class Tolerances:
    distribution_chi2_p_min: float = 0.01
    band_violation_rate_max: float = 0.02


@dataclass(frozen=True)
class SyntheticConfig:
    row_count: int
    target: Path
    seed: int
    n_customers: int
    n_products_per_category: int
    date_start: date
    date_end: date
    region_weights: dict[str, float]
    channel_weights: dict[str, float]
    category_weights: dict[str, float]
    price_bands: dict[str, tuple[float, float]]
    quantity_params: dict[str, tuple[int, int, float]]
    validation_enabled: bool
    report_path: Path
    fail_on_error: bool
    tolerances: Tolerances = field(default_factory=Tolerances)


def _require(d: Mapping[str, Any], key: str) -> Any:
    if key not in d:
        raise KeyError(f"Missing required config key: {key}")
    return d[key]


def _validate_keys(name: str, allowed: set[str], weights: Mapping[str, Any]) -> None:
    bad = set(weights) - allowed
    if bad:
        raise ValueError(f"Unknown {name} values in weights: {sorted(bad)}")
    if not weights:
        raise ValueError(f"{name} weights must be non-empty")


def load_config(path: str | Path) -> SyntheticConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    row_count = int(_require(payload, "row_count"))
    target = Path(_require(payload, "target"))

    generation = _require(payload, "generation")
    seed = int(_require(generation, "seed"))
    catalog = _require(generation, "catalog")
    n_customers = int(_require(catalog, "n_customers"))
    n_products = int(_require(catalog, "n_products_per_category"))
    date_range = _require(generation, "date_range")
    date_start = date.fromisoformat(_require(date_range, "start"))
    date_end = date.fromisoformat(_require(date_range, "end"))
    if date_end < date_start:
        raise ValueError("date_range.end must be >= date_range.start")

    validation = _require(payload, "validation")
    validation_enabled = bool(validation.get("enabled", True))
    report_path = Path(validation.get("report_path", "data/raw/quality_report.json"))
    fail_on_error = bool(validation.get("fail_on_error", False))
    tol_raw = validation.get("tolerances", {})
    tolerances = Tolerances(
        distribution_chi2_p_min=float(tol_raw.get("distribution_chi2_p_min", 0.01)),
        band_violation_rate_max=float(tol_raw.get("band_violation_rate_max", 0.02)),
    )

    controls = _require(payload, "controls")
    vds = _require(controls, "value_distributions")
    region_weights = {str(k): float(v) for k, v in _require(vds, "region").items()}
    channel_weights = {str(k): float(v) for k, v in _require(vds, "channel").items()}
    category_weights = {str(k): float(v) for k, v in _require(vds, "category").items()}
    _validate_keys("region", {r.value for r in Region}, region_weights)
    _validate_keys("channel", {c.value for c in Channel}, channel_weights)
    _validate_keys("category", {c.value for c in ProductCategory}, category_weights)

    bands_raw = _require(controls, "price_bands")
    price_bands: dict[str, tuple[float, float]] = {}
    for cat, band in bands_raw.items():
        if cat not in {c.value for c in ProductCategory}:
            raise ValueError(f"price_bands references unknown category: {cat}")
        lo, hi = float(band["min"]), float(band["max"])
        if lo > hi:
            raise ValueError(f"price_bands.{cat}: min must be <= max")
        price_bands[cat] = (lo, hi)

    qty_raw = _require(controls, "quantity_distribution")
    quantity_params: dict[str, tuple[int, int, float]] = {}
    for cat, q in qty_raw.items():
        if cat not in {c.value for c in ProductCategory}:
            raise ValueError(f"quantity_distribution references unknown category: {cat}")
        qmin, qmax, qmean = int(q["min"]), int(q["max"]), float(q["mean"])
        if qmin > qmax:
            raise ValueError(f"quantity_distribution.{cat}: min must be <= max")
        quantity_params[cat] = (qmin, qmax, qmean)

    return SyntheticConfig(
        row_count=row_count,
        target=target,
        seed=seed,
        n_customers=n_customers,
        n_products_per_category=n_products,
        date_start=date_start,
        date_end=date_end,
        region_weights=region_weights,
        channel_weights=channel_weights,
        category_weights=category_weights,
        price_bands=price_bands,
        quantity_params=quantity_params,
        validation_enabled=validation_enabled,
        report_path=report_path,
        fail_on_error=fail_on_error,
        tolerances=tolerances,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_config.py -v`
Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datagen/config.py tests/datagen/__init__.py tests/datagen/test_config.py
git commit -m "feat(datagen): SyntheticConfig loader"
```

---

## Task 2: SalesCatalog + build_catalog (schema.py)

**Files:**
- Create: `src/datagen/schema.py`
- Test: `tests/datagen/test_schema.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/test_schema.py`:
```python
"""Tests for sales catalog builder."""

from __future__ import annotations

import numpy as np
import pytest

from src.datagen.schema import SalesCatalog, build_catalog
from src.sales_data.domain.models import Customer, Product
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
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_schema.py -v`
Expected: import error.

- [ ] **Step 3: Implement schema.py**

Create `src/datagen/schema.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_schema.py -v`
Expected: 8/8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datagen/schema.py tests/datagen/test_schema.py
git commit -m "feat(datagen): SalesCatalog with seeded Faker"
```

---

## Task 3: OrderGenerator + generate_orders (generator.py)

**Files:**
- Create: `src/datagen/generator.py`
- Test: `tests/datagen/test_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/test_generator.py`:
```python
"""Tests for synthetic order generator."""

from __future__ import annotations

from collections import Counter
from datetime import date

import numpy as np
import pytest

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


def _run(seed: int):
    cfg = _Cfg()
    cfg.seed = seed
    rng = np.random.default_rng(seed)
    catalog = build_catalog(cfg, rng)
    return generate_orders(catalog, cfg, rng)


def test_row_count_exact():
    orders = _run(11)
    assert len(orders) == 200


def test_order_ids_unique_and_padded():
    orders = _run(11)
    ids = [o.order_id for o in orders]
    assert len(set(ids)) == len(ids)
    assert orders[0].order_id == "ORD-000000"
    assert orders[-1].order_id == "ORD-000199"


def test_determinism_same_seed():
    a = _run(11)
    b = _run(11)
    assert [(o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price, o.order_date, o.region, o.channel) for o in a] == \
           [(o.order_id, o.customer_id, o.product_id, o.quantity, o.unit_price, o.order_date, o.region, o.channel) for o in b]


def test_different_seeds_differ():
    a = _run(11)
    b = _run(12)
    assert a != b


def test_categorical_values_in_enums():
    orders = _run(11)
    regions = {r.value for r in Region}
    channels = {c.value for c in Channel}
    for o in orders:
        assert o.region in regions
        assert o.channel in channels


def _build_and_generate(seed: int):
    cfg = _Cfg()
    cfg.seed = seed
    rng = np.random.default_rng(seed)
    catalog = build_catalog(cfg, rng)
    orders = generate_orders(catalog, cfg, rng)
    return cfg, catalog, orders


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
    orders = _run(11)
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
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_generator.py -v`
Expected: import error.

- [ ] **Step 3: Implement generator.py**

Create `src/datagen/generator.py`:
```python
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
```

Note: `Order` carries `customer_id` / `product_id` only — names and category live on `Customer` / `Product`. Tests above already use the catalog as source of truth.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_generator.py -v`
Expected: all PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/datagen/generator.py tests/datagen/test_generator.py
git commit -m "feat(datagen): deterministic OrderGenerator"
```

---

## Task 4: write_csv (writer.py) — joins catalog metadata onto orders

**Files:**
- Create: `src/datagen/writer.py`
- Test: `tests/datagen/test_writer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/test_writer.py`:
```python
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
    assert df["order_date"].iloc[0].count("-") == 2  # ISO YYYY-MM-DD
    pd.to_datetime(df["order_date"])  # parses cleanly
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_writer.py -v`
Expected: import error.

- [ ] **Step 3: Implement writer.py**

Create `src/datagen/writer.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_writer.py -v`
Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datagen/writer.py tests/datagen/test_writer.py
git commit -m "feat(datagen): CSV writer joining catalog metadata"
```

---

## Task 5: QualityReport dataclasses (reports.py)

**Files:**
- Create: `src/datagen/reports.py`
- Test: `tests/datagen/test_reports.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/test_reports.py`:
```python
"""Tests for quality report serialization."""

from __future__ import annotations

import json
from pathlib import Path

from src.datagen.reports import (
    DistributionCheck,
    QualityReport,
    SchemaCheck,
    Violation,
    compute_config_hash,
    write_report,
)


def _sample_report() -> QualityReport:
    return QualityReport(
        summary={
            "pass": True,
            "schema_pass": True,
            "distribution_pass": True,
            "row_count": 1000,
            "generated_at": "2026-05-12T14:23:00Z",
        },
        schema=SchemaCheck(passed=True, violations=[]),
        distributions={
            "region": DistributionCheck(
                observed={"North America": 500, "Europe": 300, "Asia Pacific": 200},
                expected={"North America": 0.5, "Europe": 0.3, "Asia Pacific": 0.2},
                chi2=0.0,
                p_value=1.0,
                passed=True,
            ),
        },
        config_hash="sha256:abcd",
    )


def test_report_to_dict_roundtrip():
    r = _sample_report()
    d = r.to_dict()
    assert d["summary"]["pass"] is True
    assert d["schema"]["passed"] is True
    assert d["distributions"]["region"]["p_value"] == 1.0
    assert d["config_hash"] == "sha256:abcd"


def test_write_report_writes_json(tmp_path: Path):
    r = _sample_report()
    path = tmp_path / "report.json"
    written = write_report(r, path)
    assert written == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["row_count"] == 1000


def test_compute_config_hash_stable_under_reorder():
    a = {"x": 1, "y": [1, 2, 3], "z": {"b": 2, "a": 1}}
    b = {"y": [1, 2, 3], "z": {"a": 1, "b": 2}, "x": 1}
    assert compute_config_hash(a) == compute_config_hash(b)


def test_compute_config_hash_changes_on_value_change():
    a = {"x": 1}
    b = {"x": 2}
    assert compute_config_hash(a) != compute_config_hash(b)


def test_violation_serializes():
    v = Violation(kind="missing_column", field="order_id", detail="not found")
    assert v.to_dict() == {"kind": "missing_column", "field": "order_id", "detail": "not found"}
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_reports.py -v`
Expected: import error.

- [ ] **Step 3: Implement reports.py**

Create `src/datagen/reports.py`:
```python
"""Quality report dataclasses + JSON serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Violation:
    kind: str
    field: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "field": self.field, "detail": self.detail}


@dataclass(frozen=True)
class SchemaCheck:
    passed: bool
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": [v.to_dict() for v in self.violations]}


@dataclass(frozen=True)
class DistributionCheck:
    observed: dict[str, Any]
    expected: dict[str, Any]
    chi2: float | None
    p_value: float | None
    passed: bool
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "observed": self.observed,
            "expected": self.expected,
            "chi2": self.chi2,
            "p_value": self.p_value,
            "passed": self.passed,
        }
        out.update(self.extra)
        return out


@dataclass(frozen=True)
class QualityReport:
    summary: dict[str, Any]
    schema: SchemaCheck
    distributions: dict[str, DistributionCheck]
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": dict(self.summary),
            "schema": self.schema.to_dict(),
            "distributions": {k: v.to_dict() for k, v in self.distributions.items()},
            "config_hash": self.config_hash,
        }


def write_report(report: QualityReport, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


def compute_config_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_reports.py -v`
Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datagen/reports.py tests/datagen/test_reports.py
git commit -m "feat(datagen): QualityReport dataclasses + JSON"
```

---

## Task 6: Validator (validator.py)

**Files:**
- Create: `src/datagen/validator.py`
- Test: `tests/datagen/test_validator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/datagen/test_validator.py`:
```python
"""Tests for synthetic CSV validator."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.datagen.config import Tolerances
from src.datagen.generator import generate_orders
from src.datagen.schema import build_catalog
from src.datagen.validator import validate
from src.datagen.writer import write_csv
from src.sales_data.metadata.column_definitions import EXPECTED_COLUMNS
from src.sales_data.metadata.enums import Channel, ProductCategory, Region


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
    df["region"] = "North America"  # extreme skew
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
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `uv run pytest tests/datagen/test_validator.py -v`
Expected: import error.

- [ ] **Step 3: Implement validator.py**

Create `src/datagen/validator.py`:
```python
"""Validates synthetic CSV against config: schema conformance + distributional realism."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd
from scipy.stats import chisquare

from src.datagen.reports import (
    DistributionCheck,
    QualityReport,
    SchemaCheck,
    Violation,
    compute_config_hash,
)
from src.sales_data.metadata.column_definitions import EXPECTED_COLUMNS, ORDER_FIELDS


_DTYPE_CHECKERS = {
    "str": lambda s: s.map(lambda v: isinstance(v, str)).all(),
    "int": lambda s: pd.api.types.is_integer_dtype(s),
    "float": lambda s: pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s),
    "date": lambda s: pd.to_datetime(s, errors="coerce").notna().all(),
}


class _ValCfg(Protocol):
    row_count: int
    date_start: object
    date_end: object
    region_weights: dict[str, float]
    channel_weights: dict[str, float]
    category_weights: dict[str, float]
    price_bands: dict[str, tuple[float, float]]
    quantity_params: dict[str, tuple[int, int, float]]
    tolerances: object


def _check_schema(df: pd.DataFrame) -> SchemaCheck:
    violations: list[Violation] = []

    expected = set(EXPECTED_COLUMNS)
    actual = set(df.columns)
    for missing in sorted(expected - actual):
        violations.append(Violation("missing_column", missing, "column not present"))
    for extra in sorted(actual - expected):
        violations.append(Violation("extra_column", extra, "unexpected column"))

    if list(df.columns)[: len(EXPECTED_COLUMNS)] != EXPECTED_COLUMNS and not (expected - actual) and not (actual - expected):
        violations.append(Violation("column_order", ",".join(df.columns), "column order does not match ORDER_FIELDS"))

    for field in ORDER_FIELDS:
        if field.name not in df.columns:
            continue
        checker = _DTYPE_CHECKERS.get(field.dtype)
        if checker is None:
            continue
        try:
            ok = bool(checker(df[field.name].dropna()))
        except Exception:
            ok = False
        if not ok:
            violations.append(Violation("dtype", field.name, f"expected {field.dtype}"))

        if not field.nullable and df[field.name].isna().any():
            violations.append(Violation("null", field.name, "null in non-nullable column"))

    if "order_id" in df.columns and not df["order_id"].is_unique:
        violations.append(Violation("duplicate", "order_id", "order_id has duplicates"))

    return SchemaCheck(passed=not violations, violations=violations)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to > 0")
    return {k: v / total for k, v in weights.items()}


def _chi2_check(
    series: pd.Series,
    weights: dict[str, float],
    p_min: float,
) -> DistributionCheck:
    expected_p = _normalize(weights)
    keys = list(expected_p.keys())
    observed_counts = {k: int((series == k).sum()) for k in keys}
    total = sum(observed_counts.values())
    expected_counts = [expected_p[k] * total for k in keys]
    observed_arr = [observed_counts[k] for k in keys]
    if total == 0:
        return DistributionCheck(observed_counts, expected_p, None, None, False)
    chi2, p_value = chisquare(f_obs=observed_arr, f_exp=expected_counts)
    return DistributionCheck(
        observed=observed_counts,
        expected=expected_p,
        chi2=float(chi2),
        p_value=float(p_value),
        passed=bool(p_value > p_min),
    )


def _price_band_check(df: pd.DataFrame, bands: dict[str, tuple[float, float]], max_rate: float) -> DistributionCheck:
    violations = 0
    for cat, (lo, hi) in bands.items():
        sub = df[df["category"] == cat]["unit_price"]
        violations += int(((sub < lo) | (sub > hi)).sum())
    total = len(df)
    rate = violations / total if total else 1.0
    return DistributionCheck(
        observed={},
        expected={},
        chi2=None,
        p_value=None,
        passed=bool(rate <= max_rate),
        extra={"violation_rate": float(rate), "max_rate": float(max_rate), "violations": violations},
    )


def _quantity_check(df: pd.DataFrame, qp: dict[str, tuple[int, int, float]], max_rate: float) -> DistributionCheck:
    violations = 0
    for cat, (qmin, qmax, _) in qp.items():
        sub = df[df["category"] == cat]["quantity"]
        violations += int(((sub < qmin) | (sub > qmax)).sum())
    total = len(df)
    rate = violations / total if total else 1.0
    return DistributionCheck(
        observed={},
        expected={},
        chi2=None,
        p_value=None,
        passed=bool(rate <= max_rate),
        extra={"violation_rate": float(rate), "max_rate": float(max_rate), "violations": violations},
    )


def _date_range_check(df: pd.DataFrame, start, end) -> DistributionCheck:
    parsed = pd.to_datetime(df["order_date"], errors="coerce").dt.date
    in_range = parsed.between(start, end)
    rate = float(1 - in_range.mean()) if len(parsed) else 1.0
    return DistributionCheck(
        observed={},
        expected={},
        chi2=None,
        p_value=None,
        passed=bool(rate == 0.0),
        extra={"out_of_range_rate": rate, "start": str(start), "end": str(end)},
    )


def _config_hash(cfg: _ValCfg) -> str:
    payload = {
        "row_count": cfg.row_count,
        "date_start": str(cfg.date_start),
        "date_end": str(cfg.date_end),
        "region": cfg.region_weights,
        "channel": cfg.channel_weights,
        "category": cfg.category_weights,
        "price_bands": {k: list(v) for k, v in cfg.price_bands.items()},
        "quantity": {k: list(v) for k, v in cfg.quantity_params.items()},
    }
    return compute_config_hash(payload)


def validate(csv_path: Path | str, config: _ValCfg) -> QualityReport:
    df = pd.read_csv(Path(csv_path))
    p_min = float(config.tolerances.distribution_chi2_p_min)  # type: ignore[attr-defined]
    rate_max = float(config.tolerances.band_violation_rate_max)  # type: ignore[attr-defined]

    schema = _check_schema(df)
    distributions: dict[str, DistributionCheck] = {}
    if "region" in df.columns:
        distributions["region"] = _chi2_check(df["region"], config.region_weights, p_min)
    if "channel" in df.columns:
        distributions["channel"] = _chi2_check(df["channel"], config.channel_weights, p_min)
    if "category" in df.columns:
        distributions["category"] = _chi2_check(df["category"], config.category_weights, p_min)
    if {"category", "unit_price"} <= set(df.columns):
        distributions["price_bands"] = _price_band_check(df, config.price_bands, rate_max)
    if {"category", "quantity"} <= set(df.columns):
        distributions["quantity"] = _quantity_check(df, config.quantity_params, rate_max)
    if "order_date" in df.columns:
        distributions["date_range"] = _date_range_check(df, config.date_start, config.date_end)

    schema_pass = schema.passed
    dist_pass = all(c.passed for c in distributions.values())
    summary = {
        "pass": schema_pass and dist_pass,
        "schema_pass": schema_pass,
        "distribution_pass": dist_pass,
        "row_count": int(len(df)),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return QualityReport(
        summary=summary,
        schema=schema,
        distributions=distributions,
        config_hash=_config_hash(config),
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/datagen/test_validator.py -v`
Expected: 8/8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/datagen/validator.py tests/datagen/test_validator.py
git commit -m "feat(datagen): schema + distribution validator"
```

---

## Task 7: CLI entries (generate.py, validate.py)

**Files:**
- Create: `src/datagen/generate.py`
- Create: `src/datagen/validate.py`

No new tests; CLIs are thin wrappers covered by integration verification.

- [ ] **Step 1: Implement generate.py**

Create `src/datagen/generate.py`:
```python
"""CLI: generate synthetic sales CSV from config."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from src.datagen.config import load_config
from src.datagen.generator import generate_orders
from src.datagen.reports import write_report
from src.datagen.schema import build_catalog
from src.datagen.validator import validate
from src.datagen.writer import write_csv


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic sales CSV")
    parser.add_argument("--config", default="data/sample/synthetic_config.json", help="Path to synthetic config JSON")
    parser.add_argument("--seed", type=int, default=None, help="Override config seed")
    parser.add_argument("--rows", type=int, default=None, help="Override row count")
    parser.add_argument("--target", default=None, help="Override output CSV path")
    parser.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run validation after generation",
    )
    parser.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Exit non-zero when validation fails",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    cfg = load_config(args.config)
    if args.seed is not None:
        cfg = replace(cfg, seed=args.seed)
    if args.rows is not None:
        cfg = replace(cfg, row_count=args.rows)
    if args.target is not None:
        cfg = replace(cfg, target=Path(args.target))
    if args.validate is not None:
        cfg = replace(cfg, validation_enabled=args.validate)
    if args.fail_on_error is not None:
        cfg = replace(cfg, fail_on_error=args.fail_on_error)

    rng = np.random.default_rng(cfg.seed)
    logger.info("Building catalog (%d customers, %d products/category)", cfg.n_customers, cfg.n_products_per_category)
    catalog = build_catalog(cfg, rng)

    logger.info("Generating %d orders", cfg.row_count)
    orders = generate_orders(catalog, cfg, rng)

    written = write_csv(orders, catalog, cfg.target)
    logger.info("Wrote %s", written)

    if cfg.validation_enabled:
        logger.info("Validating %s", written)
        report = validate(written, cfg)
        report_path = write_report(report, cfg.report_path)
        logger.info(
            "Quality report at %s: pass=%s schema=%s dist=%s",
            report_path,
            report.summary["pass"],
            report.summary["schema_pass"],
            report.summary["distribution_pass"],
        )
        if cfg.fail_on_error and not report.summary["pass"]:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Implement validate.py**

Create `src/datagen/validate.py`:
```python
"""CLI: validate an existing synthetic sales CSV against config."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from src.datagen.config import load_config
from src.datagen.reports import write_report
from src.datagen.validator import validate


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate synthetic sales CSV against config")
    parser.add_argument("--config", default="data/sample/synthetic_config.json", help="Path to synthetic config JSON")
    parser.add_argument("--csv", default=None, help="Path to CSV (defaults to config.target)")
    parser.add_argument("--report-path", default=None, help="Override report output path")
    parser.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Exit non-zero when validation fails",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    cfg = load_config(args.config)
    if args.report_path is not None:
        cfg = replace(cfg, report_path=Path(args.report_path))
    if args.fail_on_error is not None:
        cfg = replace(cfg, fail_on_error=args.fail_on_error)

    csv_path = Path(args.csv) if args.csv else cfg.target
    report = validate(csv_path, cfg)
    written = write_report(report, cfg.report_path)
    logger.info(
        "Quality report at %s: pass=%s schema=%s dist=%s",
        written,
        report.summary["pass"],
        report.summary["schema_pass"],
        report.summary["distribution_pass"],
    )
    if cfg.fail_on_error and not report.summary["pass"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit**

```bash
git add src/datagen/generate.py src/datagen/validate.py
git commit -m "feat(datagen): generate + validate CLI entries"
```

---

## Task 8: Update sample config to sales-flavored

**Files:**
- Modify: `data/sample/synthetic_config.sample.json`

- [ ] **Step 1: Replace contents**

Overwrite `data/sample/synthetic_config.sample.json` with:
```json
{
  "row_count": 1000,
  "target": "data/raw/sales_1k.csv",
  "generation": {
    "seed": 42,
    "catalog": {"n_customers": 120, "n_products_per_category": 8},
    "date_range": {"start": "2024-01-01", "end": "2024-12-31"}
  },
  "validation": {
    "enabled": true,
    "report_path": "data/raw/quality_report.json",
    "fail_on_error": false,
    "tolerances": {
      "distribution_chi2_p_min": 0.01,
      "band_violation_rate_max": 0.02
    }
  },
  "controls": {
    "value_distributions": {
      "region": {"North America": 50, "Europe": 30, "Asia Pacific": 20},
      "channel": {"Online": 60, "Retail": 30, "Distributor": 10},
      "category": {"Electronics": 50, "Stationery": 30, "Furniture": 20}
    },
    "price_bands": {
      "Electronics": {"min": 15.0, "max": 500.0},
      "Stationery": {"min": 1.5, "max": 25.0},
      "Furniture": {"min": 30.0, "max": 800.0}
    },
    "quantity_distribution": {
      "Electronics": {"min": 1, "max": 5, "mean": 1.6},
      "Stationery": {"min": 1, "max": 20, "mean": 6.0},
      "Furniture": {"min": 1, "max": 3, "mean": 1.2}
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add data/sample/synthetic_config.sample.json
git commit -m "feat(datagen): sales-flavored synthetic config template"
```

---

## Task 9: Update /project:datagen slash command

**Files:**
- Modify: `.claude/commands/datagen.md`

- [ ] **Step 1: Rewrite command**

Overwrite `.claude/commands/datagen.md`:
```markdown
# /project:datagen

Run synthetic sales data generation + quality validation.

## Steps

1. Verify `data/sample/synthetic_config.json` exists. If only `synthetic_config.sample.json` is present, copy it:
   ```
   cp data/sample/synthetic_config.sample.json data/sample/synthetic_config.json
   ```
2. Run generation (also runs validation by default):
   ```
   uv run python -m src.datagen.generate
   ```
3. Report row count of generated CSV and `summary.pass` from the quality report.

If `$ARGUMENTS` is `validate`, run validation only:
```
uv run python -m src.datagen.validate
```

Generated CSVs and `quality_report.json` land in `data/raw/` (gitignored).
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/datagen.md
git commit -m "docs(datagen): update slash command for sales pipeline"
```

---

## Task 10: End-to-end run + MEMORY.md update

**Files:**
- Create: `data/sample/synthetic_config.json` (local, gitignored — copy from `.sample.json`)
- Modify: `.claude/MEMORY.md`

- [ ] **Step 1: Seed local config**

Run (PowerShell):
```
Copy-Item data/sample/synthetic_config.sample.json data/sample/synthetic_config.json
```

- [ ] **Step 2: Run full pipeline**

Run:
```
uv run python -m src.datagen.generate
```
Expected: exit 0, log lines `Wrote data\raw\sales_1k.csv` and `pass=True`.

- [ ] **Step 3: Re-run with same seed for byte-identical check**

Run (PowerShell):
```
Copy-Item data/raw/sales_1k.csv data/raw/sales_1k_run1.csv
uv run python -m src.datagen.generate
Compare-Object (Get-Content data/raw/sales_1k.csv) (Get-Content data/raw/sales_1k_run1.csv)
```
Expected: no output from Compare-Object (identical files).

- [ ] **Step 4: Cleanup transient file**

```
Remove-Item data/raw/sales_1k_run1.csv
```

- [ ] **Step 5: Full test suite green**

Run: `uv run pytest tests/datagen/ -v`
Expected: all PASS.

- [ ] **Step 6: Update MEMORY.md**

In `.claude/MEMORY.md`, update the date stamp to today and:
- Under `### ✅ Done`, add: `- Synthetic sales data pipeline (datagen) — config loader, catalog, generator, writer, validator with schema + chi-square distribution checks`
- Under `### ⚠️ Untracked`, remove the `src/datagen/` line (it is now tracked and working) and the `synthetic_config.json` line (kept locally, gitignored — that is intentional, not "need decision")
- Keep the `data/sample/sample_schema.xlsx` entry — that file is unrelated to the new sales pipeline

- [ ] **Step 7: Commit**

```bash
git add .claude/MEMORY.md
git commit -m "chore: update MEMORY.md after datagen sales pipeline"
```

---

## Definition of done

- All tasks' tests pass: `uv run pytest tests/datagen/ -v`
- `uv run python -m src.datagen.generate` produces `data/raw/sales_1k.csv` and `data/raw/quality_report.json` with `summary.pass = true`
- Same seed → byte-identical CSV (verified in Task 10 Step 3)
- `src/datagen/_kyc_legacy/` exists with all 9 original scripts; no `__init__.py` there
- `.claude/MEMORY.md` reflects new status
