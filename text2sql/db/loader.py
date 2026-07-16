"""Step 3 — SQLite loader.

Creates tables from schema.json DDL and bulk-loads CSVs.
Works with the v2 multi-domain schema via metadata.utils helpers.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from text2sql.metadata.utils import get_all_tables, load_schema

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH  = Path(__file__).parent / "sales.db"

_SQL_TYPE = {"INTEGER": "INTEGER", "TEXT": "TEXT", "REAL": "REAL", "DATE": "TEXT", "DATETIME": "TEXT"}


def _ddl(table: dict) -> str:
    col_defs = []
    for col in table["columns"]:
        sql_type = _SQL_TYPE.get(col["type"], "TEXT")
        pk   = " PRIMARY KEY" if col.get("primary_key") else ""
        null = "" if col.get("nullable", True) else " NOT NULL"
        col_defs.append(f'    "{col["name"]}" {sql_type}{pk}{null}')
    return f'CREATE TABLE IF NOT EXISTS "{table["name"]}" (\n' + ",\n".join(col_defs) + "\n)"


def _create_tables(conn: sqlite3.Connection, tables: list[dict]) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    for table in tables:
        cur.execute(_ddl(table))
    conn.commit()


def _load_csvs(conn: sqlite3.Connection, tables: list[dict]) -> None:
    for table in tables:
        csv_path = DATA_DIR / f"{table['name']}.csv"
        if not csv_path.exists():
            print(f"  [skip] {csv_path.name} not found")
            continue
        df = pd.read_csv(csv_path)
        df.to_sql(table["name"], conn, if_exists="replace", index=False)
        print(f"  [{table.get('domain', '?'):10s}]  {len(df):>6,} rows  →  {table['name']}")


def load(db_path: Path = DB_PATH) -> sqlite3.Connection:
    schema = load_schema()
    tables = get_all_tables(schema)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _create_tables(conn, tables)
    _load_csvs(conn, tables)
    return conn


if __name__ == "__main__":
    conn = load()
    conn.close()
    print(f"\nDatabase ready: {DB_PATH}")
