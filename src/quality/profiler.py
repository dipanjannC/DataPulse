"""PROFILE — descriptive, scipy-free data profiling for the generated CSVs.

Complements the validator's pass/fail *gate* with a *description* of the data a
human can read: per-column completeness, cardinality, numeric spread, and
categorical frequency. Pure over already-loaded DataFrames (no I/O), driven by
``schema.json`` (via ``metadata.utils``) so each column is profiled according to
its declared role.

Deliberately descriptive, not inferential: there is **no** goodness-of-fit /
chi-square here. That would require ``schema.json`` to declare expected
distributions (it doesn't) and would pull in ``scipy`` (this deploy omits it) —
see ``docs/quality.md``. We can *show* the observed frequency/spread; we cannot
*gate* on an expected shape that was never declared.

Every value emitted is a native Python scalar — numpy types are unwrapped and
``NaN``/``inf`` become ``None`` — so the profile serializes straight to JSON
(Starlette's encoder rejects both numpy scalars and ``NaN``).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.metadata.utils import get_all_tables

logger = logging.getLogger(__name__)

_NUMERIC_TYPES = {"INTEGER", "REAL"}
_TEMPORAL_TYPES = {"DATE", "DATETIME"}

_TOP_N = 12          # categorical values surfaced as frequency bars
_HIST_BINS = 12      # numeric sparkline resolution (capped at the distinct count)
_TEXT_AS_CATEGORICAL_MAX = 20  # a free-text column at/below this distinct count
                               # still earns a frequency view (e.g. country: 3 values)


# ── JSON-safe scalar coercion ────────────────────────────────────────────────

def _num(x) -> float | None:
    """A finite native float, or None for NaN/inf/non-numeric. Keeps the profile
    JSON-serializable — the stdlib/Starlette encoder rejects numpy scalars and NaN."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def _round(x, ndigits: int = 2) -> float | None:
    v = _num(x)
    return None if v is None else round(v, ndigits)


# ── column role → which extras a column earns ────────────────────────────────

def _role(col: dict) -> str:
    if col.get("primary_key"):
        return "key"
    if col.get("foreign_key"):
        return "reference"
    if col.get("allowed_values"):
        return "categorical"
    if col["type"] in _NUMERIC_TYPES:
        return "numeric"
    if col["type"] in _TEMPORAL_TYPES:
        return "datetime"
    return "text"


# ── per-role statistics (all scipy-free) ─────────────────────────────────────

def _numeric_stats(s: pd.Series) -> dict:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return {"min": None, "max": None, "mean": None, "std": None,
                "p25": None, "p50": None, "p75": None, "histogram": None}
    return {
        "min": _round(s.min()),
        "max": _round(s.max()),
        "mean": _round(s.mean()),
        "std": _round(s.std()),
        "p25": _round(s.quantile(0.25)),
        "p50": _round(s.quantile(0.50)),
        "p75": _round(s.quantile(0.75)),
        "histogram": _histogram(s),
    }


def _histogram(s: pd.Series) -> dict | None:
    arr = s.to_numpy(dtype=float)
    lo, hi = float(arr.min()), float(arr.max())
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return None
    if lo == hi:  # a single distinct value — one full bar
        return {"edges": [_round(lo), _round(hi)], "counts": [int(arr.size)]}
    bins = int(min(_HIST_BINS, max(1, s.nunique())))
    counts, edges = np.histogram(arr, bins=bins)
    return {"edges": [_round(e) for e in edges.tolist()],
            "counts": [int(c) for c in counts.tolist()]}


def _categorical_stats(s: pd.Series, col: dict) -> dict:
    vc = s.astype(str).value_counts()
    # Deterministic order: most frequent first, ties broken by value.
    items = sorted(vc.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))
    top = [{"value": str(k), "count": int(v)} for k, v in items[:_TOP_N]]
    out: dict = {"top": top, "other": int(sum(v for _, v in items[_TOP_N:]))}
    allowed = col.get("allowed_values")
    if allowed:
        present = {str(k) for k in vc.index}
        allowed_str = [str(a) for a in allowed]
        out["allowed"] = allowed_str
        # Declared vocabulary that never appears — a real signal the generator
        # under-samples (or the schema over-declares) a category.
        out["unused"] = [a for a in allowed_str if a not in present]
    return out


def _temporal_stats(s: pd.Series) -> dict:
    dt = pd.to_datetime(s, errors="coerce").dropna()
    if dt.empty:
        return {"min": None, "max": None}
    return {"min": str(dt.min().date()), "max": str(dt.max().date())}


# ── per-column / per-table / whole-dataset assembly ──────────────────────────

def _profile_column(series: pd.Series, col: dict) -> dict:
    n = int(len(series))
    non_null = series.dropna()
    kept = int(len(non_null))
    nulls = n - kept
    distinct = int(non_null.nunique())
    role = _role(col)

    prof: dict = {
        "type": col["type"],
        "role": role,
        "count": kept,
        "nulls": nulls,
        "null_pct": round(nulls / n * 100, 1) if n else 0.0,
        "distinct": distinct,
        "distinct_pct": round(distinct / kept * 100, 1) if kept else 0.0,
    }

    if role == "numeric":
        prof.update(_numeric_stats(non_null))
    elif role == "categorical":
        prof.update(_categorical_stats(non_null, col))
    elif role == "datetime":
        prof.update(_temporal_stats(non_null))
    elif role == "text" and distinct <= _TEXT_AS_CATEGORICAL_MAX:
        # Low-cardinality free text (e.g. customers.country) reads best as a
        # frequency breakdown, even without a declared vocabulary.
        prof.update(_categorical_stats(non_null, col))

    return prof


def _profile_table(table: dict, df: pd.DataFrame | None) -> dict:
    if df is None:
        return {"domain": table.get("domain"), "row_count": 0,
                "column_count": len(table["columns"]), "columns": {}}
    columns: dict[str, dict] = {}
    for col in table["columns"]:
        if col["name"] in df.columns:
            columns[col["name"]] = _profile_column(df[col["name"]], col)
    return {
        "domain": table.get("domain"),
        "row_count": int(len(df)),
        "column_count": len(table["columns"]),
        "columns": columns,
    }


def profile_frames(frames: Mapping[str, pd.DataFrame], schema: dict) -> dict:
    """Descriptive profile of already-loaded DataFrames. Pure — no I/O.

    Shape: ``{table_name: {domain, row_count, column_count, columns: {col: {...}}}}``.
    Iteration is schema-driven, so a table declared-but-absent profiles as an
    empty (row_count 0) entry rather than being silently dropped.
    """
    return {t["name"]: _profile_table(t, frames.get(t["name"])) for t in get_all_tables(schema)}
