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
from text2sql.agent.agent import RateLimitExhausted


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
