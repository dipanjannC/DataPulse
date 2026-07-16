"""Helpers for reading the v2 multi-domain schema.json."""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.json"


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def get_all_tables(schema: dict) -> list[dict]:
    """Return a flat list of table dicts, each with an added 'domain' key."""
    tables = []
    for domain in schema["domains"]:
        for table in domain["tables"]:
            tables.append({**table, "domain": domain["name"]})
    return tables


def get_all_relationships(schema: dict) -> list[dict]:
    """Return a flat list of all FK relationship dicts across all domains."""
    rels = []
    for domain in schema["domains"]:
        rels.extend(domain.get("relationships", []))
    return rels


def get_domains(schema: dict) -> list[dict]:
    """Return domain-level metadata (name, description)."""
    return [{"name": d["name"], "description": d["description"]} for d in schema["domains"]]
