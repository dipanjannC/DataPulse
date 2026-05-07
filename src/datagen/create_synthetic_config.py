from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from scripts.generate_semantic_values import DEFAULT_PROMPT_PATH as DEFAULT_SEMANTIC_PROMPT_PATH
from src.services.synthetic_data_generator import DEFAULT_PROMPT_PATH
from src.utils.helpers import configure_logging

DEFAULT_OUTPUT_PATH = Path("data/metadata/synthetic_config.sample.json")
DEFAULT_SOURCE = Path("data/metadata/kyc_complete.xlsx")
DEFAULT_TARGET = Path("data/synthetic")
DEFAULT_MIMESIS_DIR = Path("data/mimesis")
DEFAULT_QUALITY_REPORT_PATH = Path("quality_report.json")

logger = logging.getLogger(__name__)


def _read_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def build_synthetic_config_template(
    source: Path = DEFAULT_SOURCE,
    rows: int = 100,
    target: Path = DEFAULT_TARGET,
    mode: str = "auto",
    model_id: str | None = None,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    semantic_prompt_path: Path = DEFAULT_SEMANTIC_PROMPT_PATH,
    seed: int | None = 42,
    mimesis_artifact_dir: Path = DEFAULT_MIMESIS_DIR,
    quality_enabled: bool = True,
    quality_report_path: Path = DEFAULT_QUALITY_REPORT_PATH,
    fail_on_quality_error: bool = False,
    value_distributions: dict[str, Any] | None = None,
    demographics: dict[str, Any] | None = None,
    semantic_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": str(source),
        "row_count": rows,
        "target": str(target),
        "model": {
            "mode": mode,
            "model_id": model_id,
            "prompt_path": str(prompt_path),
            "semantic_prompt_path": str(semantic_prompt_path),
        },
        "generation": {
            "seed": seed,
            "mimesis_artifact_dir": str(mimesis_artifact_dir),
        },
        "validation": {
            "enabled": quality_enabled,
            "report_path": str(quality_report_path),
            "fail_on_error": fail_on_quality_error,
        },
        "controls": {
            "value_distributions": value_distributions or {},
            "demographics": demographics or {},
            "semantic_values": semantic_values or {},
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a single unified config for synthetic data generation")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH, help="Path to write unified config JSON")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Metadata file path")
    parser.add_argument("--rows", type=int, default=100, help="Default row count")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Synthetic CSV output directory")
    parser.add_argument(
        "--mode",
        choices=["auto", "llm", "deterministic"],
        default="auto",
        help="Generation mode to put in config",
    )
    parser.add_argument("--model-id", default=None, help="Optional Bedrock model id")
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH, help="Prompt path for LLM mapping")
    parser.add_argument(
        "--semantic-prompt-path",
        default=DEFAULT_SEMANTIC_PROMPT_PATH,
        help="Prompt path for semantic value generation",
    )
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic behavior")
    parser.add_argument("--mimesis-artifact-dir", default=DEFAULT_MIMESIS_DIR, help="Mimesis artifact output directory")
    parser.add_argument(
        "--validate-quality",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable quality validation section in generated config",
    )
    parser.add_argument(
        "--quality-report-path",
        default=DEFAULT_QUALITY_REPORT_PATH,
        help="Quality report output path (relative to target during generation)",
    )
    parser.add_argument(
        "--fail-on-quality-error",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether generated config should fail synthetic run when quality checks fail",
    )
    parser.add_argument(
        "--distribution-config",
        default=None,
        help="Optional existing distributions JSON to inline into unified config",
    )
    parser.add_argument(
        "--demographics-config",
        default=None,
        help="Optional existing demographics JSON to inline into unified config",
    )
    parser.add_argument(
        "--semantic-values-config",
        default=None,
        help="Optional existing semantic values JSON to inline into unified config",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = _parse_args()
    try:
        value_distributions = _read_optional_json(Path(args.distribution_config)) if args.distribution_config else {}
        demographics = _read_optional_json(Path(args.demographics_config)) if args.demographics_config else {}
        semantic_values = _read_optional_json(Path(args.semantic_values_config)) if args.semantic_values_config else {}

        config = build_synthetic_config_template(
            source=Path(args.source),
            rows=args.rows,
            target=Path(args.target),
            mode=args.mode,
            model_id=args.model_id,
            prompt_path=Path(args.prompt_path),
            semantic_prompt_path=Path(args.semantic_prompt_path),
            seed=args.seed,
            mimesis_artifact_dir=Path(args.mimesis_artifact_dir),
            quality_enabled=bool(args.validate_quality),
            quality_report_path=Path(args.quality_report_path),
            fail_on_quality_error=bool(args.fail_on_quality_error),
            value_distributions=value_distributions,
            demographics=demographics,
            semantic_values=semantic_values,
        )

        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        logger.info("Unified synthetic config saved to %s", output_path)
    except Exception:
        logger.exception("Failed to create synthetic config template")
        raise


if __name__ == "__main__":
    main()
