"""Step 4 — Sentence-transformer embedding pipeline.

Embeds each column's description as:
    "{table_name}.{column_name}: {description}"

Returns a dict keyed by "table.column" → List[float] (384-dim, L2-normalised).
Works with both the v1 flat schema and the v2 multi-domain schema.
"""
from __future__ import annotations

from pathlib import Path

from sentence_transformers import SentenceTransformer

from text2sql.metadata.utils import get_all_tables, load_schema

MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _column_text(table_name: str, col: dict) -> str:
    return f"{table_name}.{col['name']}: {col['description']}"


def build_column_embeddings(schema: dict | None = None) -> dict[str, list[float]]:
    """Embed every column in the schema. Returns {table.column: vector}."""
    if schema is None:
        schema = load_schema()

    tables = get_all_tables(schema)
    keys, texts = [], []
    for table in tables:
        for col in table["columns"]:
            keys.append(f"{table['name']}.{col['name']}")
            texts.append(_column_text(table["name"], col))

    vectors = _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return {k: v.tolist() for k, v in zip(keys, vectors)}


def embed_query(question: str) -> list[float]:
    """Embed a natural-language question for vector similarity search."""
    return _get_model().encode([question], normalize_embeddings=True)[0].tolist()


if __name__ == "__main__":
    embeddings = build_column_embeddings()
    sample_key = next(iter(embeddings))
    print(f"Embedded {len(embeddings)} columns  |  dim={len(embeddings[sample_key])}")
