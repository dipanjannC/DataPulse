"""GENERATE — the single sourcing point for categorical vocabularies.

Domain generators draw categorical membership from here instead of inline
literals, so ``schema.json`` is the one authority for valid values. Built once
at import from the catalog; ``values_for`` returns the list in schema.json order,
which equals each generation site's historical population order — the invariant
that keeps ``generate(seed)`` byte-identical. Weights and repetition-weighted
populations stay in the generators; only the membership set lives here.
"""

from __future__ import annotations

from src.metadata.utils import get_categorical_values, load_schema

VOCAB: dict[str, list[str]] = get_categorical_values(load_schema())


def values_for(table: str, column: str) -> list[str]:
    """Return the declared allowed values for ``table.column`` (a fresh copy)."""
    return list(VOCAB[f"{table}.{column}"])
