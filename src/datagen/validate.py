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
