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
