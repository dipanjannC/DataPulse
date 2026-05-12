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
