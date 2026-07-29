"""API endpoints — boundary-mocked, no live services.

/api/health: the connected/stale/unreachable branches of the kg_fresh mapping
(via the single `_kg_probe` boundary), plus the invariant that a stale KG is
informational and never degrades `status`.

/api/query: the graceful failure envelopes — config / kg_unavailable /
rate_limited / llm_unavailable / internal — asserting a friendly `error_kind`
and message, and that no raw exception text leaks to the client.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from groq import APIConnectionError
from neo4j.exceptions import ServiceUnavailable

import src.api.main as main
from src.embeddings.embed import MODEL_NAME
from src.knowledge_graph.freshness import kg_fingerprint
from src.metadata.utils import load_schema
from text2sql.agent.agent import AgentResult, RateLimitExhausted, Step


def test_health_reports_fresh_when_stored_fingerprint_matches(monkeypatch):
    fp = kg_fingerprint(load_schema(), MODEL_NAME)
    monkeypatch.setattr(main, "_kg_probe",
                        lambda *a: {"connected": True, "fingerprint": fp, "built_at": "2026-01-01T00:00:00Z"})
    body = TestClient(main.app).get("/api/health").json()

    assert body["kg_connected"] is True
    assert body["kg_fresh"] is True
    assert body["kg_built_at"] == "2026-01-01T00:00:00Z"


def test_health_reports_stale_but_status_stays_ok(monkeypatch):
    # connected + a non-matching fingerprint -> kg_fresh False, yet status is
    # still "ok": staleness is informational, never a health gate.
    monkeypatch.setattr(main, "_kg_probe",
                        lambda *a: {"connected": True, "fingerprint": "sha256:stale", "built_at": None})
    body = TestClient(main.app).get("/api/health").json()

    assert body["kg_connected"] is True
    assert body["kg_fresh"] is False
    assert body["status"] == "ok"  # tracked sales.db present + connected


def test_health_fresh_unknown_when_unreachable(monkeypatch):
    monkeypatch.setattr(main, "_kg_probe",
                        lambda *a: {"connected": False, "fingerprint": None, "built_at": None})
    body = TestClient(main.app).get("/api/health").json()

    assert body["kg_connected"] is False
    assert body["kg_fresh"] is None
    assert body["status"] == "degraded"


# ── /api/query graceful failure envelopes ───────────────────────────────────

_CTX = {"tables": {}, "joins": [], "domains": [], "metrics": []}


def test_query_config_missing_is_friendly(monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["success"] is False and body["error_kind"] == "config"


def test_query_kg_unavailable_is_friendly(monkeypatch):
    def boom(*a, **k):
        raise ServiceUnavailable("Unable to retrieve routing information from server")
    monkeypatch.setattr(main, "retrieve_schema_context", boom)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["success"] is False
    assert body["error_kind"] == "kg_unavailable"
    assert "knowledge graph" in body["error"].lower()
    # the raw driver exception must NOT leak into the user-facing message
    assert "ServiceUnavailable" not in body["error"] and "routing" not in body["error"]


def test_query_rate_limited_preserves_context(monkeypatch):
    monkeypatch.setattr(main, "retrieve_schema_context", lambda *a, **k: _CTX)

    def boom(*a, **k):
        raise RateLimitExhausted("daily quota")
    monkeypatch.setattr(main, "answer_question", boom)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["error_kind"] == "rate_limited"
    assert body["schema_context"] == _CTX  # panel context still shown on a rate-limit


def test_query_llm_unavailable_is_friendly(monkeypatch):
    monkeypatch.setattr(main, "retrieve_schema_context", lambda *a, **k: _CTX)

    def boom(*a, **k):
        raise APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
    monkeypatch.setattr(main, "answer_question", boom)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["error_kind"] == "llm_unavailable"
    assert "language model" in body["error"].lower()


def test_query_unexpected_error_is_friendly_internal(monkeypatch):
    monkeypatch.setattr(main, "retrieve_schema_context", lambda *a, **k: _CTX)

    def boom(*a, **k):
        raise ValueError("some internal bug")
    monkeypatch.setattr(main, "answer_question", boom)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["error_kind"] == "internal"
    assert "some internal bug" not in body["error"]  # raw cause not leaked


def test_error_envelope_carries_grounded_none(monkeypatch):
    # every failure envelope keeps the contract uniform: grounded present, null
    monkeypatch.delenv("NEO4J_URI", raising=False)
    body = TestClient(main.app).post("/api/query", json={"question": "hi"}).json()
    assert body["error_kind"] == "config"
    assert body["grounded"] is None
    assert body["grounded_reason"] is None


# ── honest success + advisory grounding on /api/query ───────────────────────

def _agent_result(answer, *, stopped="final", last_result=None, ran_sql=True):
    trace = []
    if ran_sql:
        trace.append(Step("tool", "run_sql", {"sql": "SELECT 1"}, "1 rows"))
    if stopped == "max_steps":
        trace.append(Step("stopped", None, {}, "hit max_steps=6"))
    else:
        trace.append(Step("final", None, {}, answer[:80]))
    return AgentResult(answer, trace, stopped, "SELECT 1" if ran_sql else None, last_result)


def _wire_agent(monkeypatch, result):
    monkeypatch.setattr(main, "retrieve_schema_context", lambda *a, **k: _CTX)
    monkeypatch.setattr(main, "answer_question", lambda *a, **k: result)


def test_query_success_true_and_grounded_when_answer_matches_rows(monkeypatch):
    result = _agent_result(
        "Total revenue is 7,782,964.89.",
        last_result={"columns": ["r"], "rows": [[7782964.89]], "row_count": 1},
    )
    _wire_agent(monkeypatch, result)
    body = TestClient(main.app).post("/api/query", json={"question": "revenue?"}).json()
    assert body["success"] is True
    assert body["grounded"] is True
    assert body["error"] is None and body["error_kind"] is None


def test_query_success_but_ungrounded_flags_caveat(monkeypatch):
    # SQL ran and a final answer came back (success), but the stated figure is the
    # invoices number, absent from the rows -> advisory grounded=False caveat.
    result = _agent_result(
        "Revenue is 2,030,281.53.",
        last_result={"columns": ["r"], "rows": [[7782964.89]], "row_count": 1},
    )
    _wire_agent(monkeypatch, result)
    body = TestClient(main.app).post("/api/query", json={"question": "revenue?"}).json()
    assert body["success"] is True          # honest success is about the run, not accuracy
    assert body["grounded"] is False        # grounding is advisory, never gates success
    assert "not found" in body["grounded_reason"].lower()


def test_query_max_steps_is_not_success_and_cites_last_result(monkeypatch):
    # A max_steps stop (answer="") must NOT report success even though a query ran;
    # the failure message cites the last result (best-effort synthesis).
    result = _agent_result(
        "", stopped="max_steps",
        last_result={"columns": ["n"], "rows": [[1]], "row_count": 1},
    )
    _wire_agent(monkeypatch, result)
    body = TestClient(main.app).post("/api/query", json={"question": "q"}).json()
    assert body["success"] is False
    assert body["error_kind"] == "no_result"
    assert "returned 1 row" in body["error"]
    assert body["grounded"] is False


def test_query_final_answer_without_sql_is_not_success(monkeypatch):
    # The agent concluded with prose but never ran SQL -> not a data-backed answer.
    result = _agent_result(
        "These tables are in separate domains and cannot be joined.",
        last_result=None, ran_sql=False,
    )
    _wire_agent(monkeypatch, result)
    body = TestClient(main.app).post("/api/query", json={"question": "link them"}).json()
    assert body["success"] is False
    assert body["grounded"] is False
    assert body["error_kind"] == "no_result"
    assert body["answer"]  # the explanation is still surfaced to the user


# ── /api/quality (validator verdict + descriptive profile) ──────────────────

from src.quality.reports import QualityReport, SchemaCheck


def _fake_quality_report() -> QualityReport:
    return QualityReport(
        summary={"schema_pass": True, "referential_integrity_pass": True,
                 "table_count": 1, "total_rows": 2, "violation_count": 0},
        schema=SchemaCheck(passed=True, violations=[]),
        distributions={},
        profile={"customers": {"domain": "Sales", "row_count": 2, "column_count": 1,
                               "columns": {"id": {"type": "INTEGER", "role": "key",
                                                  "count": 2, "nulls": 0, "null_pct": 0.0,
                                                  "distinct": 2, "distinct_pct": 100.0}}}},
        config_hash="sha256:test",
    )


def test_quality_returns_verdict_and_profile(monkeypatch):
    monkeypatch.setattr(main, "_quality_cache", {"sig": None, "payload": None})
    monkeypatch.setattr(main, "_data_signature", lambda d: "sig-1")
    monkeypatch.setattr(main, "validate_dataset", lambda d: _fake_quality_report())
    body = TestClient(main.app).get("/api/quality").json()

    assert body["available"] is True
    assert body["summary"]["schema_pass"] is True
    assert body["profile"]["customers"]["columns"]["id"]["role"] == "key"
    assert body["config_hash"] == "sha256:test"


def test_quality_reports_missing_data_gracefully(monkeypatch):
    # No CSVs on disk -> empty signature -> a friendly, non-crashing envelope.
    monkeypatch.setattr(main, "_quality_cache", {"sig": None, "payload": None})
    monkeypatch.setattr(main, "_data_signature", lambda d: "")
    body = TestClient(main.app).get("/api/quality").json()

    assert body["available"] is False
    assert "no generated data" in body["error"].lower()


def test_quality_caches_until_signature_changes(monkeypatch):
    # A stable data signature must serve the second hit from cache (no recompute).
    monkeypatch.setattr(main, "_quality_cache", {"sig": None, "payload": None})
    monkeypatch.setattr(main, "_data_signature", lambda d: "stable-sig")
    calls = {"n": 0}

    def counting(_):
        calls["n"] += 1
        return _fake_quality_report()

    monkeypatch.setattr(main, "validate_dataset", counting)
    client = TestClient(main.app)
    client.get("/api/quality")
    client.get("/api/quality")
    assert calls["n"] == 1
