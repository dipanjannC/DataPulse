"""Static reference-table data, extracted from the domain generators so the
literal rows live as data (JSON), not code.

These tables are **SQLite data only** — not KG nodes, not vocabularies. The
generators load them into DataFrames. Rows with a dynamic field carry a
placeholder the generator fills **in place** (preserving column order and the
rng/faker call sequence that keeps ``generate(seed)`` byte-identical):
  - ``regions.manager_name``          -> ``null``   (filled with ``fake.name()``)
  - ``customer_segments.customer_count`` -> ``[lo, hi]`` (filled with ``rng.randint(lo, hi)``)
"""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).parent


def load_fixture(name: str) -> list[dict]:
    """Return the reference rows for ``name`` as a fresh list of dicts (safe for
    the generators to mutate in place)."""
    return json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))
