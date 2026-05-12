from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.services.metadata_extractor import MetadataExtractor
from src.services.ingest_metadata import MetadataIngestor
from src.domain.metadata.definitions import TableDefinition
from src.services.synthetic_quality_validator import validate_generated_data, write_quality_report
from src.services.synthetic_data_generator import (
    AutoSyntheticDataGenerator,
    DEFAULT_PROMPT_PATH,
    SyntheticDataGenerator,
    build_default_mapping,
    write_csv,
)
from scripts.generate_semantic_values import (
    DEFAULT_PROMPT_PATH as DEFAULT_SEMANTIC_PROMPT_PATH,
    generate_semantic_values_for_tables,
)
from src.utils.helpers import configure_logging

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc_complete.xlsx")
DEFAULT_SYNTHETIC_TARGET = Path("data/synthetic")
DEFAULT_MIMESIS_ARTIFACT_DIR = Path("data/mimesis")
DEFAULT_CONFIG_PATH = Path("data/metadata/synthetic_config.sample.json")
DEFAULT_QUALITY_REPORT_PATH = Path("data/synthetic/quality_report.json")

logger = logging.getLogger(__name__)


def _load_value_distributions(config_path: Path | None) -> dict[str, dict[str, object]]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Distribution config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Distribution config must be a JSON object")

    normalized: dict[str, dict[str, object]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized[key] = {str(option): weight for option, weight in value.items()}
    return normalized


def _load_demographics_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Demographics config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Demographics config must be a JSON object")
    return payload


def _load_semantic_values(config_path: Path | None) -> dict[str, list[str]]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Semantic values config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Semantic values config must be a JSON object")

    normalized: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        values = [str(item).strip() for item in value if str(item).strip()]
        if values:
            normalized[key] = values
    return normalized


def _load_enum_allowed_values(config_path: Path | None) -> dict[str, list[str]]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise FileNotFoundError(f"Enum allowed-values config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Enum allowed-values config must be a JSON object")

    normalized: dict[str, list[str]] = {}
    for key, values in payload.items():
        if not isinstance(key, str) or not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if cleaned:
            normalized[key] = cleaned
    return normalized


def _load_unified_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Unified config file not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Unified synthetic config must be a JSON object")
    return payload


def _nested_get(payload: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _resolve_run_config(args: argparse.Namespace) -> dict[str, Any]:
    file_config: dict[str, Any] = {}
    if args.config is not None:
        file_config = _load_unified_config(Path(args.config))

    source = args.source or _nested_get(file_config, ("source",), DEFAULT_METADATA_SOURCE)
    row_count = args.rows if args.rows is not None else _nested_get(file_config, ("row_count",), 100)
    target = args.target or _nested_get(file_config, ("target",), DEFAULT_SYNTHETIC_TARGET)

    mode = args.mode or _nested_get(file_config, ("model", "mode"), "auto")
    model_id = args.model_id if args.model_id is not None else _nested_get(file_config, ("model", "model_id"), None)
    prompt_path = args.prompt_path or _nested_get(file_config, ("model", "prompt_path"), DEFAULT_PROMPT_PATH)
    semantic_prompt_path = args.semantic_prompt_path or _nested_get(
        file_config,
        ("model", "semantic_prompt_path"),
        DEFAULT_SEMANTIC_PROMPT_PATH,
    )

    seed = args.seed if args.seed is not None else _nested_get(file_config, ("generation", "seed"), None)
    mimesis_artifact_dir = args.mimesis_artifact_dir or _nested_get(
        file_config,
        ("generation", "mimesis_artifact_dir"),
        DEFAULT_MIMESIS_ARTIFACT_DIR,
    )

    value_distributions = _nested_get(file_config, ("controls", "value_distributions"), {})
    demographics = _nested_get(file_config, ("controls", "demographics"), {})
    semantic_values = _nested_get(file_config, ("controls", "semantic_values"), {})
    enum_allowed_values = _nested_get(file_config, ("controls", "enum_allowed_values"), {})

    validate_quality = args.validate_quality if args.validate_quality is not None else _nested_get(
        file_config,
        ("validation", "enabled"),
        True,
    )
    quality_report_path = args.quality_report_path or _nested_get(
        file_config,
        ("validation", "report_path"),
        DEFAULT_QUALITY_REPORT_PATH,
    )
    fail_on_quality_gate = (
        args.fail_on_quality_gate if args.fail_on_quality_gate is not None else _nested_get(
            file_config,
            ("validation", "fail_on_error"),
            False,
        )
    )

    distribution_config_path = args.distribution_config
    demographics_config_path = args.demographics_config
    semantic_values_config_path = args.semantic_values_config

    if not distribution_config_path and value_distributions:
        distribution_config_path = "__inline__"
    if not demographics_config_path and demographics:
        demographics_config_path = "__inline__"
    if not semantic_values_config_path and semantic_values:
        semantic_values_config_path = "__inline__"

    return {
        "source": source,
        "row_count": int(row_count),
        "target": target,
        "mode": str(mode).strip().lower(),
        "model_id": model_id,
        "prompt_path": prompt_path,
        "semantic_prompt_path": semantic_prompt_path,
        "seed": seed,
        "mimesis_artifact_dir": mimesis_artifact_dir,
        "distribution_config_path": distribution_config_path,
        "demographics_config_path": demographics_config_path,
        "semantic_values_config_path": semantic_values_config_path,
        "inline_value_distributions": value_distributions if isinstance(value_distributions, Mapping) else {},
        "inline_demographics": demographics if isinstance(demographics, Mapping) else {},
        "inline_semantic_values": semantic_values if isinstance(semantic_values, Mapping) else {},
        "inline_enum_allowed_values": enum_allowed_values if isinstance(enum_allowed_values, Mapping) else {},
        "validate_quality": bool(validate_quality),
        "quality_report_path": quality_report_path,
        "fail_on_quality_gate": bool(fail_on_quality_gate),
    }


def _artifact_paths(source_path: Path, artifact_dir: Path, table_name: str) -> tuple[Path, Path]:
    stem = source_path.stem
    table_slug = "".join(ch if ch.isalnum() else "_" for ch in table_name.strip().lower()).strip("_")
    mapping_path = artifact_dir / f"{stem}_{table_slug}_mimesis_mapping.json"
    code_path = artifact_dir / f"{stem}_{table_slug}_mimesis_table_definition.py"
    return mapping_path, code_path


def _python_literal(value: object) -> str:
    return repr(value)


def _class_name_for_table(table_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in table_name).strip("_")
    parts = [part for part in cleaned.split("_") if part]
    if not parts:
        return "CustomTable"
    return "".join(part[:1].upper() + part[1:] for part in parts) + "TableDefinition"


def _render_table_class_block(table: TableDefinition, mapping: dict[str, str]) -> str:
    class_name = _class_name_for_table(table.name)
    column_entries: list[str] = []
    for column in table.columns:
        key = f"{table.name}.{column.name}"
        generator_key = mapping.get(key, "string")
        column_entries.append(
            "        \"{column}\": \"{generator}\",".format(
                column=column.name,
                generator=generator_key,
            )
        )

    metadata_entries: list[str] = []
    for column in table.columns:
        metadata_entries.append(
            "            ColumnDefinition(\n"
            f"                name={_python_literal(column.name)},\n"
            f"                type={_python_literal(column.type)},\n"
            f"                nullable={_python_literal(column.nullable)},\n"
            f"                primary_key={_python_literal(column.primary_key)},\n"
            f"                foreign_key={_python_literal(column.foreign_key)},\n"
            f"                description={_python_literal(column.description)},\n"
            f"                default_value={_python_literal(column.default_value)},\n"
            f"                allowed_values={_python_literal(list(column.allowed_values))},\n"
            f"                sample_values={_python_literal(list(column.sample_values))},\n"
            "            ),"
        )

    return (
        f"class {class_name}:\n"
        f"    table_name = {_python_literal(table.name)}\n"
        "    column_generators = {\n"
        + "\n".join(column_entries)
        + "\n    }\n\n"
        "    def __init__(self, seed: int | None = None) -> None:\n"
        "        self._generator = SyntheticDataGenerator(seed=seed, column_generators=self.column_generators)\n\n"
        "    @staticmethod\n"
        "    def table_definition() -> TableDefinition:\n"
        "        return TableDefinition(\n"
        f"            name={_python_literal(table.name)},\n"
        f"            description={_python_literal(table.description)},\n"
        f"            domain={_python_literal(table.domain)},\n"
        "            columns=[\n"
        + "\n".join(metadata_entries)
        + "\n            ],\n"
        "        )\n\n"
        "    def generate_rows(self, rows: int = 10) -> list[dict[str, object]]:\n"
        "        table = self.table_definition()\n"
        "        generated = self._generator.generate([table], row_count=rows)\n"
        "        return generated.get(self.table_name, [])\n"
    )


def _render_mimesis_table_definition_code(
    table: TableDefinition,
    mapping: dict[str, str],
) -> str:
    class_block = _render_table_class_block(table, mapping)
    class_name = _class_name_for_table(table.name)
    return (
        "from src.domain.metadata.definitions import ColumnDefinition, TableDefinition\n"
        "from src.services.synthetic_data_generator import SyntheticDataGenerator\n\n"
        "# Auto-generated custom table definitions for manual mimesis validation.\n\n"
        f"{class_block}\n\n"
        "if __name__ == \"__main__\":\n"
        "    # Quick preview for manual validation\n"
        f"    instance = {class_name}(seed=42)\n"
        "    rows = instance.generate_rows(rows=3)\n"
        f"    print(\"{class_name}:\", rows)\n"
    )


def _write_mimesis_artifacts(
    source_path: Path,
    tables: Sequence[TableDefinition],
    mapping: dict[str, str],
    artifact_dir: Path,
) -> list[Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for table in tables:
        table_mapping = {
            key: value
            for key, value in mapping.items()
            if key.split(".", 1)[0].strip().lower() == table.name.strip().lower()
        }
        mapping_path, code_path = _artifact_paths(source_path, artifact_dir, table.name)
        mapping_path.write_text(json.dumps(table_mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        code_path.write_text(
            _render_mimesis_table_definition_code(table=table, mapping=mapping),
            encoding="utf-8",
        )
        written_paths.extend([mapping_path, code_path])
    return written_paths


def run_synthetic_plan(
    source: Path | str = DEFAULT_METADATA_SOURCE,
    row_count: int = 15,
    target: Path | str = DEFAULT_SYNTHETIC_TARGET,
    model_id: str | None = None,
    prompt_path: Path | str = DEFAULT_PROMPT_PATH,
    semantic_prompt_path: Path | str = DEFAULT_SEMANTIC_PROMPT_PATH,
    seed: int | None = None,
    mimesis_artifact_dir: Path | str = DEFAULT_MIMESIS_ARTIFACT_DIR,
    distribution_config_path: Path | str | None = None,
    demographics_config_path: Path | str | None = None,
    semantic_values_config_path: Path | str | None = None,
    mode: str = "auto",
    inline_value_distributions: Mapping[str, Mapping[str, object]] | None = None,
    inline_demographics: Mapping[str, Any] | None = None,
    inline_semantic_values: Mapping[str, Sequence[str]] | None = None,
    inline_enum_allowed_values: Mapping[str, Sequence[str]] | None = None,
    enum_allowed_values_config_path: Path | str | None = None,
    validate_quality: bool = True,
    quality_report_path: Path | str = DEFAULT_QUALITY_REPORT_PATH,
    fail_on_quality_gate: bool = False,
) -> list[Path]:
    logger.info("Starting synthetic data generation")
    source_path = Path(source)
    logger.info("Loading metadata from %s", source_path)
    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)

    enum_allowed_values = {
        str(key): [str(item).strip() for item in values if str(item).strip()]
        for key, values in (inline_enum_allowed_values or {}).items()
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes))
    }
    if enum_allowed_values_config_path:
        logger.info("Loading enum allowed-values overrides from %s", enum_allowed_values_config_path)
        enum_allowed_values = _load_enum_allowed_values(Path(enum_allowed_values_config_path))

    tables: Sequence[TableDefinition] = ingestor.ingest(
        source_path,
        enum_allowed_overrides=enum_allowed_values,
    )

    distributions: dict[str, dict[str, object]] = {
        str(key): {str(inner_key): inner_value for inner_key, inner_value in value_map.items()}
        for key, value_map in dict(inline_value_distributions or {}).items()
    }
    demographics = dict(inline_demographics or {})
    semantic_values = {
        str(key): [str(item) for item in values if str(item).strip()]
        for key, values in (inline_semantic_values or {}).items()
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes))
    }

    if distribution_config_path and distribution_config_path != "__inline__":
        logger.info("Loading value distributions from %s", distribution_config_path)
        distributions = _load_value_distributions(Path(distribution_config_path))
    if demographics_config_path and demographics_config_path != "__inline__":
        logger.info("Loading demographics config from %s", demographics_config_path)
        demographics = _load_demographics_config(Path(demographics_config_path))
    if semantic_values_config_path and semantic_values_config_path != "__inline__":
        logger.info("Loading semantic values config from %s", semantic_values_config_path)
        semantic_values = _load_semantic_values(Path(semantic_values_config_path))

    mapping: dict[str, str]
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"auto", "llm", "deterministic"}:
        raise ValueError("mode must be one of: auto, llm, deterministic")

    if normalized_mode == "llm":
        logger.info("Generating semantic values from active metadata schema for llm mode")
        generated_semantic_values = generate_semantic_values_for_tables(
            tables=tables,
            prompt_path=semantic_prompt_path,
            model_id=model_id,
        )
        semantic_values = {
            **generated_semantic_values,
            **semantic_values,
        }

    if normalized_mode == "deterministic":
        logger.info("Running in deterministic mode (no LLM mapping)")
        mapping = build_default_mapping(tables)
        deterministic_generator = SyntheticDataGenerator(
            seed=seed,
            column_generators=mapping,
            value_distributions=distributions,
            demographics_config=demographics,
            semantic_values=semantic_values,
        )
        rows_by_table = deterministic_generator.generate(tables, row_count=row_count)
    else:
        try:
            logger.info("Running in %s mode with LLM-assisted mapping", normalized_mode)
            generator = AutoSyntheticDataGenerator(
                model_id=model_id,
                prompt_path=Path(prompt_path),
                seed=seed,
                value_distributions=distributions,
                demographics_config=demographics,
                semantic_values=semantic_values,
            )
            rows_by_table, mapping = generator.generate_with_mapping(tables, row_count=row_count)
        except Exception:
            if normalized_mode == "llm":
                logger.exception("LLM mode failed during synthetic generation")
                raise
            logger.exception("LLM mapping failed in auto mode, falling back to deterministic mapping")
            mapping = build_default_mapping(tables)
            fallback_generator = SyntheticDataGenerator(
                seed=seed,
                column_generators=mapping,
                value_distributions=distributions,
                demographics_config=demographics,
                semantic_values=semantic_values,
            )
            rows_by_table = fallback_generator.generate(tables, row_count=row_count)

    output_path = Path(target)
    logger.info("Writing synthetic CSV files to %s", output_path)
    csv_paths = write_csv(output_path, tables, rows_by_table)

    written_paths: list[Path] = [*csv_paths]
    if validate_quality:
        report_target = Path(quality_report_path)
        if not report_target.is_absolute():
            report_target = output_path / report_target
        logger.info("Running synthetic data quality validation")
        quality_report = validate_generated_data(tables=tables, data_dir=output_path)
        report_path = write_quality_report(quality_report, report_target)
        written_paths.append(report_path)
        if fail_on_quality_gate and not bool(_nested_get(quality_report, ("summary", "pass"), False)):
            raise RuntimeError(
                "Synthetic quality gate failed. See validation report at "
                f"{report_path} for referential integrity and quality metrics."
            )

    logger.info("Writing mimesis artifacts to %s", mimesis_artifact_dir)
    artifact_paths = _write_mimesis_artifacts(
        source_path=source_path,
        tables=tables,
        mapping=mapping,
        artifact_dir=Path(mimesis_artifact_dir),
    )
    written_paths.extend(artifact_paths)
    logger.info("Synthetic generation finished successfully")
    return written_paths


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic data and mimesis mapping artifacts")
    parser.add_argument(
        "--config",
        default=None,
        help="Unified JSON config path for source/model/controls/output settings",
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to metadata JSON or Excel",
    )
    parser.add_argument("--rows", type=int, default=None, help="Number of rows to generate per table")
    parser.add_argument("--target", default=None, help="Output directory for CSV files")
    parser.add_argument(
        "--mode",
        choices=["auto", "llm", "deterministic"],
        default=None,
        help="Generation mode: auto (LLM with fallback), llm (LLM only), deterministic (no LLM)",
    )
    parser.add_argument("--model-id", default=None, help="Optional Bedrock model ID")
    parser.add_argument("--prompt-path", default=None, help="Prompt template path")
    parser.add_argument(
        "--semantic-prompt-path",
        default=None,
        help="Prompt template path used for LLM semantic value generation",
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed for deterministic generation")
    parser.add_argument(
        "--distribution-config",
        default=None,
        help="Path to JSON config that controls weighted distributions per column (e.g. ID type proportions)",
    )
    parser.add_argument(
        "--demographics-config",
        default=None,
        help="Path to JSON config for demographic controls (country share, DOB age buckets)",
    )
    parser.add_argument(
        "--semantic-values-config",
        default=None,
        help="Path to JSON config containing semantically curated values per column",
    )
    parser.add_argument(
        "--mimesis-artifact-dir",
        default=None,
        help="Output directory for interim mimesis mapping/code artifacts",
    )
    parser.add_argument(
        "--validate-quality",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable post-generation quality checks and summary report",
    )
    parser.add_argument(
        "--quality-report-path",
        default=None,
        help="Path for quality report JSON (relative paths resolve under synthetic target)",
    )
    parser.add_argument(
        "--fail-on-quality-gate",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Fail run when quality report summary.pass is false",
    )
    return parser.parse_args()



def main() -> None:
    configure_logging()
    args = _parse_args()
    try:
        run_config = _resolve_run_config(args)
        paths = run_synthetic_plan(**run_config)
        for path in paths:
            logger.info("Synthetic data saved to %s", path)
    except Exception:
        logger.exception("Synthetic data generation failed")
        raise


if __name__ == "__main__":
    main()
