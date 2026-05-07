from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from src.services.metadata_extractor import MetadataExtractor
from src.services.ingest_metadata import MetadataIngestor
from src.domain.metadata.definitions import TableDefinition
from src.services.ddl_generator import generate_ddl

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc_complete.xlsx")


def _default_ddl_target(source: Path) -> Path:
    return Path("data/ddl") / f"{source.stem}_generated.sql"


def run_generate_ddl(
    source: Path | str = DEFAULT_METADATA_SOURCE,
    ddl_target: Path | str | None = None,
) -> Path:
    source_path = Path(source)
    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)
    tables: Sequence[TableDefinition] = ingestor.ingest(source_path)

    ddl_text = generate_ddl(tables, dialect="postgres")

    ddl_path = Path(ddl_target) if ddl_target else _default_ddl_target(source_path)
    ddl_path.parent.mkdir(parents=True, exist_ok=True)
    ddl_path.write_text(ddl_text, encoding="utf-8")
    return ddl_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PostgreSQL SQL DDL")
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_METADATA_SOURCE,
        help="Path to metadata JSON or Excel",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path for DDL SQL",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    path = run_generate_ddl(source=args.source, ddl_target=args.out)
    print(f"Generated DDL saved to {path}")


if __name__ == "__main__":
    main()
