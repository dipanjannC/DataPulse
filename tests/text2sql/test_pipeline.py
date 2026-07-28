"""Orchestrator gate decision — the enforcement teeth of the quality gate.

``main()`` itself needs Neo4j creds to run end-to-end, so the abort/continue
decision is extracted into a pure helper and unit-tested here across all four
(fail_on_error x schema.passed) combinations.
"""

from __future__ import annotations

from src.pipeline import _should_abort
from src.quality.reports import QualityReport, SchemaCheck, Violation


def _report(passed: bool) -> QualityReport:
    violations = [] if passed else [Violation("null", "t.c", "null in non-nullable column")]
    return QualityReport(
        summary={}, schema=SchemaCheck(passed=passed, violations=violations),
        distributions={}, config_hash="sha256:x",
    )


def test_hard_gate_aborts_on_violations():
    assert _should_abort(_report(False), fail_on_error=True) is True


def test_warn_only_continues_despite_violations():
    assert _should_abort(_report(False), fail_on_error=False) is False


def test_clean_data_never_aborts():
    assert _should_abort(_report(True), fail_on_error=True) is False
    assert _should_abort(_report(True), fail_on_error=False) is False
