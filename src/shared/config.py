"""Application-wide configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Central configuration for DataPulse."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])

    raw_data_dir: Path = field(default=None)
    processed_data_dir: Path = field(default=None)
    sample_data_dir: Path = field(default=None)

    neo4j_uri: str = field(default_factory=lambda: os.environ.get("NEO4J_URI", ""))
    neo4j_username: str = field(default_factory=lambda: os.environ.get("NEO4J_USERNAME", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.environ.get("NEO4J_PASSWORD", ""))

    google_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-flash-latest"))

    def __post_init__(self) -> None:
        if self.raw_data_dir is None:
            self.raw_data_dir = self.project_root / "data" / "raw"
        if self.processed_data_dir is None:
            self.processed_data_dir = self.project_root / "data" / "processed"
        if self.sample_data_dir is None:
            self.sample_data_dir = self.project_root / "data" / "sample"
