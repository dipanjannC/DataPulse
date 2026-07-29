"""kg_fingerprint / is_kg_fresh: pure KG-staleness detection."""

from __future__ import annotations

from src.knowledge_graph.freshness import is_kg_fresh, kg_fingerprint


def _schema() -> dict:
    return {
        "version": "1",
        "domains": [{
            "name": "D", "description": "d",
            "tables": [{
                "name": "t", "description": "x",
                "columns": [{"name": "c", "type": "TEXT", "allowed_values": ["A", "B"]}],
            }],
        }],
    }


def test_fingerprint_is_deterministic_and_tagged():
    s = _schema()
    assert kg_fingerprint(s, "m") == kg_fingerprint(s, "m")
    assert kg_fingerprint(s, "m").startswith("sha256:")


def test_fingerprint_changes_on_any_schema_edit_including_reorder():
    base = kg_fingerprint(_schema(), "m")
    reordered = _schema()
    reordered["domains"][0]["tables"][0]["columns"][0]["allowed_values"] = ["B", "A"]
    assert kg_fingerprint(reordered, "m") != base  # order is part of the fingerprint


def test_fingerprint_changes_on_model_change():
    s = _schema()
    assert kg_fingerprint(s, "model-1") != kg_fingerprint(s, "model-2")


def test_is_kg_fresh_true_on_match_false_on_drift():
    s = _schema()
    fp = kg_fingerprint(s, "m")
    assert is_kg_fresh(fp, s, "m") is True

    drifted = _schema()
    drifted["domains"][0]["tables"][0]["columns"].append({"name": "d", "type": "TEXT"})
    assert is_kg_fresh(fp, drifted, "m") is False


def test_missing_fingerprint_is_not_fresh():
    assert is_kg_fresh(None, _schema(), "m") is False
    assert is_kg_fresh("", _schema(), "m") is False
