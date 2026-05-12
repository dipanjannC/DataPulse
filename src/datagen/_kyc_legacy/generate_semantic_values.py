from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from src.config.bedrock_config import BedrockConfig
from src.domain.metadata.definitions import ColumnDefinition, TableDefinition
from src.infrastructure.aws.bedrock_client import BedrockClient
from src.services.ingest_metadata import MetadataIngestor
from src.services.metadata_extractor import MetadataExtractor
from src.utils.helpers import _base_type, configure_logging

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc_complete.xlsx")
DEFAULT_PROMPT_PATH = Path("src/prompts/semantic_value_list.md")
DEFAULT_OUTPUT_PATH = Path("data/metadata/semantic_values.generated.json")

logger = logging.getLogger(__name__)


def _extract_text_from_response(response_text: str) -> str:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text.strip()

    if isinstance(payload, dict) and "content" in payload:
        content = payload["content"]
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and "text" in first:
                return str(first["text"]).strip()
        if isinstance(content, str):
            return content.strip()
    return response_text.strip()


def _try_parse_json(content: str) -> dict[str, list[str]] | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        snippet = content[start : end + 1]
        try:
            payload = json.loads(snippet)
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None

    normalized: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            normalized[key] = cleaned
    return normalized


def _is_text_candidate(column: ColumnDefinition) -> bool:
    if column.primary_key or column.foreign_key:
        return False
    return _base_type(column.type) == "string"


def _heuristic_values(column: ColumnDefinition) -> list[str]:
    if column.allowed_values:
        return list(column.allowed_values)[:5]
    if column.sample_values:
        return list(column.sample_values)[:5]
    name = column.name.lower()
    if "state" in name:
        return ["California", "Texas", "New York", "Florida", "Washington"]
    if "city" in name:
        return ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
    if "country" in name:
        return ["United States", "India", "United Kingdom", "Singapore", "United Arab Emirates"]
    if "occupation" in name:
        return ["Engineer", "Teacher", "Doctor", "Accountant", "Analyst"]
    if "id_type" in name or "identifier_type" in name:
        return ["SSN", "STATE_ID", "PASSPORT", "DRIVER_LICENSE", "NATIONAL_ID"]
    return []


def _fallback_semantic_values(tables: Sequence[TableDefinition]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for table in tables:
        for column in table.columns:
            if not _is_text_candidate(column):
                continue
            values = _heuristic_values(column)
            if values:
                output[f"{table.name}.{column.name}"] = values
    return output


def _schema_payload(tables: Sequence[TableDefinition]) -> dict[str, object]:
    return {
        "tables": [
            {
                "name": table.name,
                "description": table.description,
                "columns": [
                    {
                        "name": column.name,
                        "type": column.type,
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "foreign_key": column.foreign_key,
                        "description": column.description,
                        "allowed_values": list(column.allowed_values),
                        "sample_values": list(column.sample_values),
                    }
                    for column in table.columns
                ],
            }
            for table in tables
        ]
    }


def generate_semantic_values_for_tables(
    tables: Sequence[TableDefinition],
    prompt_path: Path | str = DEFAULT_PROMPT_PATH,
    model_id: str | None = None,
) -> dict[str, list[str]]:
    semantic_values: dict[str, list[str]] | None = None
    try:
        logger.info("Attempting LLM-assisted semantic value generation")
        prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        prompt = prompt_template.replace("{{SCHEMA}}", json.dumps(_schema_payload(tables), indent=2))
        client = BedrockClient(BedrockConfig(model_id=model_id) if model_id else BedrockConfig())
        response_text = client.send_prompt(prompt, max_tokens=4096, temperature=0.1)
        content = _extract_text_from_response(response_text)
        semantic_values = _try_parse_json(content)
    except Exception:
        logger.exception("LLM semantic value generation failed; switching to deterministic fallback")
        semantic_values = None

    if not semantic_values:
        logger.info("Using heuristic semantic value fallback")
        semantic_values = _fallback_semantic_values(tables)
    return semantic_values


def run_generate_semantic_values(
    source: Path | str = DEFAULT_METADATA_SOURCE,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    prompt_path: Path | str = DEFAULT_PROMPT_PATH,
    model_id: str | None = None,
) -> Path:
    logger.info("Generating semantic values from metadata")
    source_path = Path(source)
    logger.info("Loading metadata from %s", source_path)
    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)
    tables = ingestor.ingest(source_path)
    semantic_values = generate_semantic_values_for_tables(
        tables=tables,
        prompt_path=prompt_path,
        model_id=model_id,
    )

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(semantic_values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("Semantic values saved to %s", target_path)
    return target_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate semantic value lists for synthetic data columns")
    parser.add_argument("source", nargs="?", default=DEFAULT_METADATA_SOURCE, help="Metadata file path")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_PATH, help="Output JSON path")
    parser.add_argument("--prompt-path", default=DEFAULT_PROMPT_PATH, help="Prompt file path")
    parser.add_argument("--model-id", default=None, help="Optional Bedrock model id override")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = _parse_args()
    try:
        path = run_generate_semantic_values(
            source=args.source,
            output_path=args.out,
            prompt_path=args.prompt_path,
            model_id=args.model_id,
        )
        logger.info("Semantic values saved to %s", path)
    except Exception:
        logger.exception("Failed to generate semantic values")
        raise


if __name__ == "__main__":
    main()
