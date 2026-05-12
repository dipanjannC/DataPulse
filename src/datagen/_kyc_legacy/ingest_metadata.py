from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.services.metadata_extractor import MetadataExtractor
from src.services.ingest_metadata import MetadataIngestor
from src.domain.metadata.definitions import TableDefinition

DEFAULT_METADATA_SOURCE = Path("data/metadata/kyc.xlsx")


def ingest_metadata(source: Path | str = DEFAULT_METADATA_SOURCE) -> Sequence[TableDefinition]:
    '''
    Ingest metadata from the specified source.
    Args:
        source: Path to the metadata JSON or Excel file.
    Returns:
        A sequence of TableDefinition objects representing the ingested metadata.
    
    '''
    source_path = Path(source)
    extractor = MetadataExtractor()
    ingestor = MetadataIngestor(extractor)
    return ingestor.ingest(source_path)


def main(source: Path | str = DEFAULT_METADATA_SOURCE) -> None:
    tables = ingest_metadata(source)
    for table in tables:
        print(f"Table {table.name} ({len(table.columns)} columns)")


if __name__ == "__main__":
    main()
