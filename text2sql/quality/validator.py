"""Schema-driven data-quality validator for the generated CSVs.

Reuses the *mechanisms* from ``src/datagen/validator.py`` (dtype checkers,
PK-uniqueness, non-null checks) but is driven by ``schema.json`` (via
``metadata.utils``) instead of the sales-hardcoded ``ORDER_FIELDS`` /
``EXPECTED_COLUMNS``.

Scope: schema conformance + referential integrity ONLY. Chi-square
distributional checks are deliberately skipped — ``schema.json`` declares no
expected distributions, and they would pull in ``scipy``, which text2sql's lean
deploy omits. That is a deliberate deferral, not an oversight; ``distributions``
is emitted empty.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from text2sql.metadata.utils import (
    get_all_relationships,
    get_all_tables,
    load_schema,
)
from text2sql.quality.reports import (
    QualityReport,
    SchemaCheck,
    Violation,
    compute_config_hash,
)

logger = logging.getLogger(__name__)


# ── dtype checkers, adapted for the CSV round-trip ──────────────────────────────
# These differ from src's on purpose: pandas reads a *nullable* INTEGER column as
# float64 (a single NULL forces the float dtype), so a verbatim `is_integer_dtype`
# check would false-positive on every nullable FK (rep_id, manager_id, ...). TEXT
# is intentionally vacuous — a CSV round-trip erases the text/number distinction,
# so any value is a valid TEXT value; the real TEXT constraint (non-null) is
# carried by the separate null check below.

def _is_integer(s: pd.Series) -> bool:
    s = s.dropna()
    if s.empty:
        return True
    if pd.api.types.is_integer_dtype(s):
        return True
    if pd.api.types.is_float_dtype(s):
        return bool((s % 1 == 0).all())
    coerced = pd.to_numeric(s, errors="coerce")
    return bool(coerced.notna().all() and (coerced % 1 == 0).all())


def _is_real(s: pd.Series) -> bool:
    s = s.dropna()
    if s.empty:
        return True
    if pd.api.types.is_numeric_dtype(s):
        return True
    return bool(pd.to_numeric(s, errors="coerce").notna().all())


def _is_datelike(s: pd.Series) -> bool:
    s = s.dropna()
    if s.empty:
        return True
    return bool(pd.to_datetime(s, errors="coerce").notna().all())


_DTYPE_CHECKERS = {
    "INTEGER": _is_integer,
    "REAL": _is_real,
    "DATE": _is_datelike,
    "DATETIME": _is_datelike,
    "TEXT": lambda s: True,
}


# ── per-table schema conformance ────────────────────────────────────────────────

def _check_table(table: dict, df: pd.DataFrame | None) -> list[Violation]:
    name = table["name"]
    if df is None:
        return [Violation("missing_table", name, "declared in schema but no CSV found")]

    violations: list[Violation] = []
    actual = set(df.columns)
    for col in table["columns"]:
        cname = col["name"]
        field = f"{name}.{cname}"
        if cname not in actual:
            violations.append(Violation("missing_column", field, "declared in schema but not present"))
            continue

        series = df[cname]
        checker = _DTYPE_CHECKERS.get(col["type"])
        if checker is not None:
            try:
                ok = bool(checker(series))
            except Exception:
                ok = False
            if not ok:
                violations.append(Violation("dtype", field, f"values not consistent with {col['type']}"))

        if not col.get("nullable", True) and series.isna().any():
            violations.append(Violation("null", field, "null present in non-nullable column"))

        if col.get("primary_key") and not series.dropna().is_unique:
            violations.append(Violation("duplicate", field, "duplicate values in primary key"))

    return violations


# ── referential integrity across the FK graph ───────────────────────────────────

def _check_referential_integrity(rel: dict, frames: Mapping[str, pd.DataFrame]) -> Violation | None:
    child = frames.get(rel["from_table"])
    parent = frames.get(rel["to_table"])
    fk, pk = rel["from_column"], rel["to_column"]
    edge = f"{rel['from_table']}.{fk} -> {rel['to_table']}.{pk}"

    # A missing table/column is already reported by _check_table; don't double-flag.
    if child is None or parent is None:
        return None
    if fk not in child.columns or pk not in parent.columns:
        return None

    parent_keys = set(parent[pk].dropna().tolist())
    fk_values = child[fk].dropna().tolist()  # nullable FKs legitimately skip NULLs
    orphans = sorted({v for v in fk_values if v not in parent_keys}, key=str)
    if not orphans:
        return None
    return Violation(
        "referential_integrity",
        edge,
        f"{len(orphans)} value(s) with no matching {rel['to_table']}.{pk}: {orphans[:10]}",
    )


# ── public API ──────────────────────────────────────────────────────────────────

def validate_frames(frames: Mapping[str, pd.DataFrame], schema: dict) -> QualityReport:
    """Validate already-loaded DataFrames against the schema. Pure — no I/O."""
    tables = get_all_tables(schema)
    violations: list[Violation] = []
    row_counts: dict[str, int] = {}

    for table in tables:
        df = frames.get(table["name"])
        row_counts[table["name"]] = 0 if df is None else int(len(df))
        violations.extend(_check_table(table, df))

    for rel in get_all_relationships(schema):
        v = _check_referential_integrity(rel, frames)
        if v is not None:
            violations.append(v)

    schema_check = SchemaCheck(passed=not violations, violations=violations)
    structural = {"missing_table", "missing_column", "dtype", "null", "duplicate"}
    summary = {
        "pass": schema_check.passed,
        "schema_pass": not any(v.kind in structural for v in violations),
        "referential_integrity_pass": not any(v.kind == "referential_integrity" for v in violations),
        "table_count": len(tables),
        "total_rows": sum(row_counts.values()),
        "violation_count": len(violations),
        "row_counts": row_counts,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return QualityReport(
        summary=summary,
        schema=schema_check,
        distributions={},  # chi-square distributional checks deliberately skipped (see module docstring)
        config_hash=_schema_hash(schema),
    )


def validate_dataset(data_dir: Path | str, schema: dict | None = None) -> QualityReport:
    """Read the CSVs under ``data_dir`` and validate them against the schema."""
    schema = schema if schema is not None else load_schema()
    data_dir = Path(data_dir)
    frames: dict[str, pd.DataFrame] = {}
    for table in get_all_tables(schema):
        csv_path = data_dir / f"{table['name']}.csv"
        if csv_path.exists():
            frames[table["name"]] = pd.read_csv(csv_path)
    return validate_frames(frames, schema)


def _schema_hash(schema: dict) -> str:
    # Structural projection so cosmetic description edits don't churn the hash.
    projection = {
        "version": schema.get("version"),
        "tables": {
            t["name"]: [
                {
                    "name": c["name"],
                    "type": c["type"],
                    "primary_key": bool(c.get("primary_key")),
                    "nullable": bool(c.get("nullable", True)),
                }
                for c in t["columns"]
            ]
            for t in get_all_tables(schema)
        },
        "relationships": sorted(
            f"{r['from_table']}.{r['from_column']}->{r['to_table']}.{r['to_column']}"
            for r in get_all_relationships(schema)
        ),
    }
    return compute_config_hash(projection)
