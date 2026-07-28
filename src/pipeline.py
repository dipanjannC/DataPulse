"""ORCHESTRATOR — end-to-end setup pipeline.

Runs the four layers in order:
    GENERATE   synthetic CSV data (seeded, per-domain registry)
    QUALITY    validate the CSVs against schema.json (the gate)
    LOAD       CSVs -> SQLite; column metadata -> Neo4j knowledge graph
    (CONSUME is the API/agent, started separately)

Usage:
    uv run python -m src.pipeline [--seed 42] [--fail-on-error]

The quality gate defaults to warn-only: the first validation of freshly
generated data is a discovery step and must not hold setup hostage. Pass
``--fail-on-error`` to promote violations to a hard gate (abort before load)
once the data is known clean.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DataPulse text2sql end-to-end setup pipeline.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for data generation (default: 42).")
    parser.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Abort before load if the quality gate finds violations (default: warn only).",
    )
    return parser.parse_args(argv)


def _should_abort(report, fail_on_error: bool) -> bool:
    """Abort before load only when the gate found violations AND the caller
    opted into hard-gating. Warn-only (the default) never aborts."""
    return fail_on_error and not report.schema.passed


def _env_ok() -> bool:
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not os.getenv(k)]
    if missing:
        logger.error("Missing environment variables: %s", ", ".join(missing))
        logger.error("Copy .env.sample -> .env and fill in your credentials.")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)

    if not _env_ok():
        return 1

    logger.info("GENERATE — synthetic data (seed=%d)", args.seed)
    from src.datagen.generate import DATA_DIR, generate
    generate(seed=args.seed)

    logger.info("QUALITY — validating generated CSVs against schema.json")
    from src.quality.reports import write_report
    from src.quality.validator import validate_dataset
    report = validate_dataset(DATA_DIR)
    report_path = write_report(report, DATA_DIR / "quality_report.json")
    logger.info("Quality report -> %s", report_path)
    logger.info(
        "  schema_pass=%s  referential_integrity_pass=%s  violations=%d  rows=%d",
        report.summary["schema_pass"], report.summary["referential_integrity_pass"],
        report.summary["violation_count"], report.summary["total_rows"],
    )
    if not report.schema.passed:
        for v in report.schema.violations[:20]:
            logger.warning("  [%s] %s: %s", v.kind, v.field, v.detail)
        if _should_abort(report, args.fail_on_error):
            logger.error("Quality gate failed and --fail-on-error is set; aborting before load.")
            return 1
        logger.warning("Quality gate found violations; continuing (warn-only). Pass --fail-on-error to hard-gate.")

    logger.info("LOAD — CSVs into SQLite")
    from src.db.loader import load
    stats = load()
    logger.info("SQLite ready: %s (%d tables, %d rows)", stats.db_path, len(stats.rows), stats.total_rows)

    logger.info("LOAD — embedding metadata + building the Neo4j knowledge graph")
    from src.knowledge_graph.builder import build
    build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )

    logger.info("Setup complete. Start the API (/start-api), then open frontend/index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
