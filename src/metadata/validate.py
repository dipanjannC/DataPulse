"""Catalog integrity — schema-internal consistency of schema.json.

Distinct from ``quality/validator.py`` (which checks generated CSVs against the
schema): this validates that the *catalog references itself* consistently, so a
relationship can never name a table or column that isn't declared. The KG
builder consumes this to skip broken relationships instead of silently writing
bogus join edges.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.metadata.utils import get_all_relationships, get_all_tables


@dataclass(frozen=True)
class SkippedRelationship:
    relationship: dict
    reason: str


@dataclass(frozen=True)
class RelationshipCheck:
    valid: list[dict]
    skipped: list[SkippedRelationship]

    @property
    def skip_reasons(self) -> list[str]:
        return [s.reason for s in self.skipped]


def check_relationships(schema: dict) -> RelationshipCheck:
    """Partition schema relationships into valid vs skipped. A relationship is
    valid only when both endpoints name a declared table AND a declared column
    on that table."""
    tables = get_all_tables(schema)
    table_names = {t["name"] for t in tables}
    columns = {t["name"]: {c["name"] for c in t["columns"]} for t in tables}

    valid: list[dict] = []
    skipped: list[SkippedRelationship] = []
    for rel in get_all_relationships(schema):
        reason = _endpoint_error(rel, table_names, columns)
        if reason is None:
            valid.append(rel)
        else:
            skipped.append(SkippedRelationship(relationship=rel, reason=reason))
    return RelationshipCheck(valid=valid, skipped=skipped)


def _endpoint_error(
    rel: dict, table_names: set[str], columns: dict[str, set[str]]
) -> str | None:
    for side in ("from", "to"):
        table = rel.get(f"{side}_table")
        column = rel.get(f"{side}_column")
        if table not in table_names:
            return f"{side}_table '{table}' is not a declared table"
        if column not in columns.get(table, set()):
            return f"{side}_column '{table}.{column}' is not a declared column"
    return None
