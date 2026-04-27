"""CSV data loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.shared.exceptions import DataLoadError


class CsvLoader:
    """Loads sales data from CSV files into pandas DataFrames."""

    def __init__(self, file_path: Path) -> None:
        self.file_path = Path(file_path)

    def load(self) -> pd.DataFrame:
        """Read the CSV and return a validated DataFrame.

        Raises:
            DataLoadError: If the file cannot be read or is malformed.
        """
        raise NotImplementedError("CsvLoader.load is not yet implemented.")
