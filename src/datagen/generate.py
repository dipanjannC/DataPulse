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
