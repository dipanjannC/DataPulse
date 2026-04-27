"""Application-wide configuration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """Central configuration for DataPulse."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    # Data paths
    raw_data_dir: Path = field(default=None)
    processed_data_dir: Path = field(default=None)
    sample_data_dir: Path = field(default=None)

    # Graph backend
    graph_backend: str = "networkx"  # "networkx" or "neo4j"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    def __post_init__(self) -> None:
        if self.raw_data_dir is None:
            self.raw_data_dir = self.project_root / "data" / "raw"
        if self.processed_data_dir is None:
            self.processed_data_dir = self.project_root / "data" / "processed"
        if self.sample_data_dir is None:
            self.sample_data_dir = self.project_root / "data" / "sample"
