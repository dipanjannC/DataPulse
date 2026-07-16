"""End-to-end setup pipeline.

Runs Steps 2–5 in order:
    Step 2  Generate synthetic CSV data
    Step 3  Load CSVs into SQLite
    Step 4  (implicit inside Step 5) Embed column metadata
    Step 5  Build the Neo4j Knowledge Graph (nodes + vector index + FK edges)

Usage:
    uv run python text2sql/pipeline.py

Then launch the UI with:
    uv run streamlit run text2sql/app/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `text2sql.*` imports resolve
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()


def _check_env() -> None:
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD") if not os.getenv(k)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("        Copy .env.sample → .env and fill in your credentials.")
        sys.exit(1)


def run() -> None:
    _check_env()

    print("=" * 60)
    print("Step 2 — Generating synthetic sales data")
    print("=" * 60)
    from text2sql.datagen.generate import generate
    generate()

    print()
    print("=" * 60)
    print("Step 3 — Loading data into SQLite")
    print("=" * 60)
    from text2sql.db.loader import load
    conn = load()
    conn.close()

    print()
    print("=" * 60)
    print("Step 4+5 — Embedding metadata + Building Knowledge Graph")
    print("=" * 60)
    from text2sql.knowledge_graph.builder import build
    build(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
    )

    print()
    print("=" * 60)
    print("Setup complete!")
    print("Launch the UI with:")
    print("    uv run streamlit run text2sql/app/app.py")
    print("=" * 60)


if __name__ == "__main__":
    run()
