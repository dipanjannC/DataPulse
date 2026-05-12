"""Tests for quality report serialization."""

from __future__ import annotations

import json
from pathlib import Path

from src.datagen.reports import (
    DistributionCheck,
    QualityReport,
    SchemaCheck,
    Violation,
    compute_config_hash,
    write_report,
)


def _sample_report() -> QualityReport:
    return QualityReport(
        summary={
            "pass": True,
            "schema_pass": True,
            "distribution_pass": True,
            "row_count": 1000,
            "generated_at": "2026-05-12T14:23:00Z",
        },
        schema=SchemaCheck(passed=True, violations=[]),
        distributions={
            "region": DistributionCheck(
                observed={"North America": 500, "Europe": 300, "Asia Pacific": 200},
                expected={"North America": 0.5, "Europe": 0.3, "Asia Pacific": 0.2},
                chi2=0.0,
                p_value=1.0,
                passed=True,
            ),
        },
        config_hash="sha256:abcd",
    )


def test_report_to_dict_roundtrip():
    r = _sample_report()
    d = r.to_dict()
    assert d["summary"]["pass"] is True
    assert d["schema"]["passed"] is True
    assert d["distributions"]["region"]["p_value"] == 1.0
    assert d["config_hash"] == "sha256:abcd"


def test_write_report_writes_json(tmp_path: Path):
    r = _sample_report()
    path = tmp_path / "report.json"
    written = write_report(r, path)
    assert written == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["row_count"] == 1000


def test_compute_config_hash_stable_under_reorder():
    a = {"x": 1, "y": [1, 2, 3], "z": {"b": 2, "a": 1}}
    b = {"y": [1, 2, 3], "z": {"a": 1, "b": 2}, "x": 1}
    assert compute_config_hash(a) == compute_config_hash(b)


def test_compute_config_hash_changes_on_value_change():
    a = {"x": 1}
    b = {"x": 2}
    assert compute_config_hash(a) != compute_config_hash(b)


def test_violation_serializes():
    v = Violation(kind="missing_column", field="order_id", detail="not found")
    assert v.to_dict() == {"kind": "missing_column", "field": "order_id", "detail": "not found"}
