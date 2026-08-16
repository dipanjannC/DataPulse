"""Step 4 — Embedding pipeline (fastembed / ONNX backend).

Embeds three levels of schema metadata so the retriever can route and seed at
the right granularity:
    Column  →  "{table_name}.{column_name}: {description}"
    Table   →  "{domain} • {table_name}: {description}"
    Domain  →  "{domain_name}: {description}"

Each returns a dict keyed by the node's identity → List[float] (384-dim,
L2-normalised). Works with both the v1 flat schema and the v2 multi-domain
schema.

fastembed replaces sentence-transformers: same all-MiniLM-L6-v2 model exported
to ONNX, ~80 MB RAM vs ~600 MB for the PyTorch version — fits on free-tier hosts.
Vectors are L2-normalised by default; compatible with the existing Neo4j indexes.
"""
from __future__ import annotations

from fastembed import TextEmbedding

from src.metadata.utils import get_all_tables, get_domains, load_schema

# Short name kept for KG freshness-stamp compatibility (stored in Neo4j :Meta node).
MODEL_NAME = "all-MiniLM-L6-v2"
# Full HuggingFace model ID used by fastembed's ONNX model registry.
_FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        # Downloads the ONNX model on first call (~45 MB), then caches locally.
        _model = TextEmbedding(_FASTEMBED_MODEL)
    return _model


def _column_text(table_name: str, col: dict) -> str:
    text = f"{table_name}.{col['name']}: {col['description']}"
    aliases = col.get("aliases")
    if aliases:
        text += f" (also known as: {', '.join(aliases)})"
    return text


def _table_text(table: dict) -> str:
    return f"{table['domain']} • {table['name']}: {table['description']}"


def _domain_text(domain: dict) -> str:
    return f"{domain['name']}: {domain['description']}"


def _encode(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    # fastembed.embed() returns a generator of numpy arrays, L2-normalised by default.
    return [v.tolist() for v in _get_model().embed(texts)]


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

    return dict(zip(keys, _encode(texts)))


def build_table_embeddings(schema: dict | None = None) -> dict[str, list[float]]:
    """Embed every table (domain + name + description). Returns {table_name: vector}."""
    if schema is None:
        schema = load_schema()

    tables = get_all_tables(schema)
    keys  = [t["name"] for t in tables]
    texts = [_table_text(t) for t in tables]
    return dict(zip(keys, _encode(texts)))


def build_domain_embeddings(schema: dict | None = None) -> dict[str, list[float]]:
    """Embed every domain (name + description). Returns {domain_name: vector}."""
    if schema is None:
        schema = load_schema()

    domains = get_domains(schema)
    keys  = [d["name"] for d in domains]
    texts = [_domain_text(d) for d in domains]
    return dict(zip(keys, _encode(texts)))


def embed_query(question: str) -> list[float]:
    """Embed a natural-language question for vector similarity search."""
    return next(_get_model().embed([question])).tolist()


if __name__ == "__main__":
    embeddings = build_column_embeddings()
    sample_key = next(iter(embeddings))
    print(f"Embedded {len(embeddings)} columns  |  dim={len(embeddings[sample_key])}")
