from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from src.config.database_config import PostgresConfig
from src.domain.metadata.definitions import TableDefinition
from src.services.ingest_metadata import MetadataIngestor
from src.services.metadata_extractor import MetadataExtractor
from src.services.postgres_loader import load_tables_from_csvs
from src.utils.helpers import _topological_tables

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc.xlsx")
DEFAULT_SYNTHETIC_SOURCE = Path("data/synthetic")


def run_load_synthetic_to_db(
    metadata_source: Path | str = DEFAULT_METADATA_SOURCE,
    synthetic_source: Path | str = DEFAULT_SYNTHETIC_SOURCE,
    truncate: bool = False,
) -> list[Path]:
    source_path = Path(metadata_source)
    data_dir = Path(synthetic_source)

    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)
    tables: Sequence[TableDefinition] = ingestor.ingest(source_path)
    ordered_table_names = [table.name for table in _topological_tables(tables)]

    config = PostgresConfig()
    config.validate_required()
    return load_tables_from_csvs(
        config=config,
        data_dir=data_dir,
        ordered_tables=ordered_table_names,
        truncate=truncate,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load generated synthetic CSVs into PostgreSQL")
    parser.add_argument(
        "metadata_source",
        nargs="?",
        default=DEFAULT_METADATA_SOURCE,
        help="Path to metadata Excel/JSON used to determine table load order",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_SYNTHETIC_SOURCE,
        help="Directory containing generated CSV files",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before loading each CSV",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    loaded_paths = run_load_synthetic_to_db(
        metadata_source=args.metadata_source,
        synthetic_source=args.data_dir,
        truncate=args.truncate,
    )
    for path in loaded_paths:
        print(f"Loaded CSV into Postgres: {path}")


if __name__ == "__main__":
    main()
