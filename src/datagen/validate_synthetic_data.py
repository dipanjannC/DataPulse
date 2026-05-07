from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.domain.metadata.definitions import TableDefinition
from src.services.ingest_metadata import MetadataIngestor
from src.services.metadata_extractor import MetadataExtractor
from src.services.synthetic_quality_validator import validate_generated_data, write_quality_report
from src.utils.helpers import configure_logging

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc_complete.xlsx")
DEFAULT_DATA_DIR = Path("data/synthetic")
DEFAULT_REPORT_PATH = Path("data/synthetic/quality_report.json")
DEFAULT_CONFIG_PATH = Path("data/metadata/synthetic_config.json")

logger = logging.getLogger(__name__)


def _nested_get(payload: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _load_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Unified config must be a JSON object")
    return payload


def _normalize_enum_overrides(raw: Mapping[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not isinstance(raw, Mapping):
        return normalized
    for key, values in raw.items():
        if not isinstance(key, str):
            continue
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if cleaned:
            normalized[key] = cleaned
    return normalized


def _load_tables(source: Path, enum_allowed_overrides: Mapping[str, Sequence[str]] | None = None) -> Sequence[TableDefinition]:
    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)
    return ingestor.ingest(source, enum_allowed_overrides=enum_allowed_overrides)


def run_validation(
    source: Path | str = DEFAULT_METADATA_SOURCE,
    data_dir: Path | str = DEFAULT_DATA_DIR,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    fail_on_error: bool | None = None,
    config_path: Path | str | None = None,
) -> Path:
    unified_config = _load_config(Path(config_path)) if config_path else {}
    resolved_source = source or _nested_get(unified_config, ("source",), DEFAULT_METADATA_SOURCE)
    resolved_data_dir = data_dir or _nested_get(unified_config, ("target",), DEFAULT_DATA_DIR)
    resolved_report_path = report_path or _nested_get(
        unified_config,
        ("validation", "report_path"),
        DEFAULT_REPORT_PATH,
    )
    resolved_fail = (
        bool(_nested_get(unified_config, ("validation", "fail_on_error"), False))
        if fail_on_error is None
        else fail_on_error
    )
    enum_overrides = _normalize_enum_overrides(_nested_get(unified_config, ("controls", "enum_allowed_values"), {}))

    source_path = Path(resolved_source)
    data_path = Path(resolved_data_dir)

    logger.info("Loading metadata from %s", source_path)
    tables = _load_tables(source_path, enum_allowed_overrides=enum_overrides)

    logger.info("Running synthetic data quality checks on %s", data_path)
    report = validate_generated_data(tables=tables, data_dir=data_path)
    output_path = Path(resolved_report_path)
    if not output_path.is_absolute():
        output_path = data_path / output_path
    output_report = write_quality_report(report=report, report_path=output_path)

    summary = report.get("summary", {})
    logger.info(
        "Quality summary: pass=%s pk=%s fk=%s enum=%s nullability=%s type=%s",
        summary.get("pass"),
        summary.get("pk_violations"),
        summary.get("fk_violations"),
        summary.get("enum_violations"),
        summary.get("nullability_violations"),
        summary.get("type_violations"),
    )

    if resolved_fail and not bool(summary.get("pass", False)):
        raise RuntimeError(f"Synthetic quality checks failed. See report: {output_report}")

    return output_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate synthetic CSV quality and referential integrity")
    parser.add_argument("source", nargs="?", default=None, help="Metadata source file")
    parser.add_argument("--data-dir", default=None, help="Synthetic CSV directory")
    parser.add_argument("--report-path", default=None, help="Output quality report JSON")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Unified synthetic config JSON")
    parser.add_argument(
        "--fail-on-error",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Exit with error when quality checks fail",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = _parse_args()
    run_validation(
        source=args.source,
        data_dir=args.data_dir,
        report_path=args.report_path,
        fail_on_error=args.fail_on_error,
        config_path=args.config,
    )


if __name__ == "__main__":
    main()
