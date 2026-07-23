"""Serialization round-trip for the harvested quality-report objects."""

from __future__ import annotations

import json

from text2sql.quality.reports import (
    DistributionCheck,
    QualityReport,
    SchemaCheck,
    Violation,
    compute_config_hash,
    write_report,
)


def _report() -> QualityReport:
    return QualityReport(
        summary={"pass": False, "violation_count": 1},
        schema=SchemaCheck(passed=False, violations=[Violation("dtype", "t.c", "bad")]),
        distributions={
            "d": DistributionCheck(
                observed={"a": 1}, expected={"a": 0.5}, chi2=1.25, p_value=0.3,
                passed=True, extra={"note": "x"},
            )
        },
        config_hash="sha256:abc",
    )


def test_quality_report_to_dict_is_json_serializable():
    d = _report().to_dict()

    assert d["summary"]["pass"] is False
    assert d["schema"]["passed"] is False
    assert d["schema"]["violations"][0] == {"kind": "dtype", "field": "t.c", "detail": "bad"}
    # DistributionCheck.extra is flattened into the dict, not nested
    assert d["distributions"]["d"]["chi2"] == 1.25
    assert d["distributions"]["d"]["note"] == "x"
    assert d["config_hash"] == "sha256:abc"
    # round-trips through JSON without loss
    assert json.loads(json.dumps(d)) == d


def test_write_report_round_trips_through_disk(tmp_path):
    report = _report()
    path = write_report(report, tmp_path / "nested" / "quality_report.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == report.to_dict()


def test_compute_config_hash_is_order_independent_and_prefixed():
    h1 = compute_config_hash({"a": 1, "b": 2})
    h2 = compute_config_hash({"b": 2, "a": 1})
    h3 = compute_config_hash({"a": 1, "b": 3})

    assert h1 == h2  # key order does not change the hash
    assert h1 != h3  # payload change does
    assert h1.startswith("sha256:")
