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

    if not (expected - actual) and not (actual - expected) and list(df.columns) != EXPECTED_COLUMNS:
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
