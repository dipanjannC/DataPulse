"""Builds a knowledge graph from sales DataFrames."""

from __future__ import annotations

import pandas as pd


class GraphBuilder:
    """Converts a sales DataFrame into graph nodes and edges."""

    def build(self, df: pd.DataFrame) -> None:
        """Parse the DataFrame and populate the graph store.

        Args:
            df: Sales DataFrame with columns matching sample_sales.csv schema.
        """
        raise NotImplementedError("GraphBuilder.build is not yet implemented.")
