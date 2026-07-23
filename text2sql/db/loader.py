"""Step 3 — SQLite loader (LOAD layer).

Creates tables from schema.json DDL and bulk-loads the generated CSVs. Fully
schema-driven via ``metadata.utils``. Opens, uses, and closes its own
connection, returning a ``LoadStats`` (rows per table) rather than a bare
``sqlite3.Connection``.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from text2sql.metadata.utils import get_all_tables, load_schema

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH  = Path(__file__).parent / "sales.db"

_SQL_TYPE = {"INTEGER": "INTEGER", "TEXT": "TEXT", "REAL": "REAL", "DATE": "TEXT", "DATETIME": "TEXT"}


@dataclass(frozen=True)
class LoadStats:
    db_path: Path
    rows: dict[str, int] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def _ddl(table: dict) -> str:
    col_defs = []
    for col in table["columns"]:
        sql_type = _SQL_TYPE.get(col["type"], "TEXT")
        pk   = " PRIMARY KEY" if col.get("primary_key") else ""
        null = "" if col.get("nullable", True) else " NOT NULL"
        col_defs.append(f'    "{col["name"]}" {sql_type}{pk}{null}')
    return f'CREATE TABLE IF NOT EXISTS "{table["name"]}" (\n' + ",\n".join(col_defs) + "\n)"


def _create_tables(conn: sqlite3.Connection, tables: list[dict]) -> None:
    # Guarantees every declared table exists (as an empty table) even if its CSV
    # is absent; the bulk load below then replaces those that do have a CSV.
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    for table in tables:
        cur.execute(_ddl(table))
    conn.commit()


def _load_csvs(conn: sqlite3.Connection, tables: list[dict], data_dir: Path) -> dict[str, int]:
    rows: dict[str, int] = {}
    for table in tables:
        csv_path = data_dir / f"{table['name']}.csv"
        if not csv_path.exists():
            logger.warning("skip %s: CSV not found", csv_path.name)
            continue
        df = pd.read_csv(csv_path)
        df.to_sql(table["name"], conn, if_exists="replace", index=False)
        rows[table["name"]] = len(df)
        logger.info("Loaded %6d rows  %-30s (%s)", len(df), table["name"], table.get("domain", "?"))
    return rows


def load(db_path: Path | str = DB_PATH, data_dir: Path | str = DATA_DIR) -> LoadStats:
    db_path = Path(db_path)
    data_dir = Path(data_dir)
    tables = get_all_tables(load_schema())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        _create_tables(conn, tables)
        rows = _load_csvs(conn, tables, data_dir)
        conn.commit()
    finally:
        conn.close()
    return LoadStats(db_path=db_path, rows=rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stats = load()
    logger.info("Database ready: %s (%d tables, %d rows)", stats.db_path, len(stats.rows), stats.total_rows)
