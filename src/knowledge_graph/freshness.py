"""KG freshness — detect when the Neo4j knowledge graph is stale vs the catalog.

The KG is built once from ``schema.json``; if the catalog (or the embedding
model) changes and the KG is not rebuilt, the graph silently diverges — the
"KG must be rebuilt, no auto-sync" gap. ``builder`` stamps a
``(:Meta {key: 'kg'})`` node carrying ``kg_fingerprint(schema, model)``; this
module recomputes that fingerprint from the current catalog so staleness is
*detectable* (surfaced by ``/api/health``) rather than silent.

Pure: no Neo4j and no embedding model here — just a stable hash of the inputs
that determine the KG build output. The model name is passed by the caller so
this module has no dependency on the (heavy) embedding layer.

Limitation (by design): the fingerprint tracks the schema content + the model
NAME, not the builder/embedding-text *code*. A change to how embedding text is
assembled won't trip it — rebuild after such a change regardless.
"""

from __future__ import annotations

from src.quality.reports import compute_config_hash


def kg_fingerprint(schema: dict, model: str) -> str:
    """Stable hash of everything that determines the KG build output: the whole
    catalog (descriptions, aliases, allowed_values, types, metrics, and
    relationships all feed nodes or embeddings) plus the embedding model name."""
    return compute_config_hash({"schema": schema, "model": model})


def is_kg_fresh(stored_fingerprint: str | None, schema: dict, model: str) -> bool:
    """True iff a fingerprint was stored on the KG and it matches the current
    catalog. A missing fingerprint (an unstamped/older KG) is treated as NOT
    fresh — it needs a rebuild to gain the staleness anchor."""
    return bool(stored_fingerprint) and stored_fingerprint == kg_fingerprint(schema, model)
