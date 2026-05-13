"""Loads a sales CSV directly into Neo4j as a knowledge graph."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

import pandas as pd

from src.graph.domain.schema import EdgeType, NodeType
from src.graph.store.neo4j_store import Neo4jStore
from src.shared.config import Settings


logger = logging.getLogger(__name__)


_MERGE_ORDER_ROW = f"""
UNWIND $rows AS row
MERGE (cust:{NodeType.CUSTOMER.value} {{customer_id: row.customer_id}})
  ON CREATE SET cust.customer_name = row.customer_name
  ON MATCH  SET cust.customer_name = row.customer_name
MERGE (cat:{NodeType.CATEGORY.value} {{name: row.category}})
MERGE (prod:{NodeType.PRODUCT.value} {{product_id: row.product_id}})
  ON CREATE SET prod.product_name = row.product_name
  ON MATCH  SET prod.product_name = row.product_name
MERGE (region:{NodeType.REGION.value} {{name: row.region}})
MERGE (channel:{NodeType.CHANNEL.value} {{name: row.channel}})
MERGE (order:{NodeType.ORDER.value} {{order_id: row.order_id}})
  ON CREATE SET order.quantity = row.quantity,
                order.unit_price = row.unit_price,
                order.order_date = date(row.order_date)
  ON MATCH  SET order.quantity = row.quantity,
                order.unit_price = row.unit_price,
                order.order_date = date(row.order_date)
MERGE (cust)-[:{EdgeType.PLACED.value}]->(order)
MERGE (order)-[:{EdgeType.CONTAINS.value}]->(prod)
MERGE (order)-[:{EdgeType.IN_REGION.value}]->(region)
MERGE (order)-[:{EdgeType.VIA_CHANNEL.value}]->(channel)
MERGE (prod)-[:{EdgeType.BELONGS_TO.value}]->(cat)
""".strip()


@dataclass(frozen=True)
class LoadStats:
    rows: int
    batches: int


class _StoreLike(Protocol):
    def setup_constraints(self) -> list[str]: ...
    def run_write(self, query: str, **params) -> list[dict]: ...
    def run_read(self, query: str, **params) -> list[dict]: ...


def _iter_batches(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _csv_to_rows(csv_path: Path) -> list[dict]:
    df = pd.read_csv(csv_path)
    df["order_date"] = df["order_date"].astype(str)
    return df.to_dict(orient="records")


class Neo4jGraphBuilder:
    """Reads a sales CSV and MERGEs nodes + edges into Neo4j."""

    def __init__(self, store: _StoreLike, *, batch_size: int = 500) -> None:
        self.store = store
        self.batch_size = batch_size

    def build_from_csv(self, csv_path: Path | str) -> LoadStats:
        path = Path(csv_path)
        logger.info("Setting up Neo4j constraints")
        self.store.setup_constraints()

        rows = _csv_to_rows(path)
        logger.info("Loading %d rows from %s", len(rows), path)

        batches = 0
        for batch in _iter_batches(rows, self.batch_size):
            self.store.run_write(_MERGE_ORDER_ROW, rows=batch)
            batches += 1
            logger.info("  ... batch %d (%d rows)", batches, len(batch))

        return LoadStats(rows=len(rows), batches=batches)

    def count_nodes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for node in NodeType:
            rows = self.store.run_read(
                f"MATCH (n:{node.value}) RETURN count(n) AS c"
            )
            out[node.value] = int(rows[0]["c"]) if rows else 0
        return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a sales CSV into Neo4j")
    parser.add_argument("--csv", default="data/raw/sales_1k.csv", help="Path to sales CSV")
    parser.add_argument("--batch-size", type=int, default=500, help="MERGE batch size")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    settings = Settings()
    with Neo4jStore.from_settings(settings) as store:
        builder = Neo4jGraphBuilder(store, batch_size=args.batch_size)
        stats = builder.build_from_csv(args.csv)
        logger.info("Loaded %d rows in %d batches", stats.rows, stats.batches)
        counts = builder.count_nodes()
        for label, c in counts.items():
            logger.info("  %s: %d", label, c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
