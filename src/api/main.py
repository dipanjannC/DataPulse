"""FastAPI backend for DataPulse Text2SQL.

The `/api/query` endpoint routes through the multi-step tool-calling agent
(`text2sql.agent.agent.answer_question`): the model discovers schema, resolves
categorical filters, and runs read-only SQL by *calling tools* over the
knowledge graph, so the response carries an explicit reasoning `trace` and a
natural-language `answer` alongside the SQL and rows.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import APIConnectionError, APIStatusError
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ConfigurationError, ServiceUnavailable, SessionExpired
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from text2sql.agent.agent import RateLimitExhausted, answer_question
from text2sql.agent.grounding import check_grounding
from src.knowledge_graph.retriever import retrieve_schema_context
from src.knowledge_graph.freshness import is_kg_fresh
from src.embeddings.embed import MODEL_NAME
from src.metadata.utils import get_domains, load_schema
from src.quality.validator import validate_dataset

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "db" / "sales.db"
DATA_DIR = Path(__file__).parent.parent / "data"

# A cold/paused Aura instance must not hang the health poll; bound it tight.
_HEALTH_TIMEOUT_S = 5

app = FastAPI(title="DataPulse Text2SQL API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    top_k: int = 10


def _kg_probe(uri: str | None, user: str | None, pwd: str | None) -> dict:
    """Bounded KG probe -> {'connected', 'fingerprint', 'built_at', 'skipped'}. Never raises.
    A cold/paused Aura instance must not hang the health poll, so timeouts are
    tight; the same bounded connection also reads the (:Meta) build stamp used
    for staleness detection."""
    if not all([uri, user, pwd]):
        return {"connected": False, "fingerprint": None, "built_at": None, "skipped": None}
    driver = None
    try:
        driver = GraphDatabase.driver(
            uri, auth=(user, pwd),
            connection_timeout=_HEALTH_TIMEOUT_S,
            connection_acquisition_timeout=_HEALTH_TIMEOUT_S,
            notifications_disabled_classifications=["DEPRECATION"],
        )
        driver.verify_connectivity()
        with driver.session() as s:
            rec = s.run(
                "MATCH (m:Meta {key: 'kg'}) "
                "RETURN m.schema_fingerprint AS fingerprint, m.built_at AS built_at, "
                "m.skipped_relationships AS skipped"
            ).single()
        return {
            "connected": True,
            "fingerprint": rec["fingerprint"] if rec else None,
            "built_at": rec["built_at"] if rec else None,
            "skipped": rec["skipped"] if rec else None,
        }
    except Exception:
        return {"connected": False, "fingerprint": None, "built_at": None, "skipped": None}
    finally:
        if driver is not None:
            driver.close()


@app.get("/api/health")
def health():
    uri = os.getenv("NEO4J_URI")
    probe = _kg_probe(uri, os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    db_exists = DB_PATH.exists()
    # kg_fresh: True/False when the graph is reachable (False = stale or unstamped),
    # None when we couldn't reach it to tell. Informational only — NOT folded into
    # `status`, so a stale KG never breaks a health-gated deploy.
    kg_fresh = is_kg_fresh(probe["fingerprint"], load_schema(), MODEL_NAME) if probe["connected"] else None
    return {
        "status": "ok" if (probe["connected"] and db_exists) else "degraded",
        "kg_uri": uri or "not configured",
        "kg_connected": probe["connected"],
        "kg_fresh": kg_fresh,
        "kg_skipped_relationships": probe.get("skipped"),
        "kg_built_at": probe["built_at"],
        "db_exists": db_exists,
    }


@app.get("/api/domains")
def list_domains():
    schema = load_schema()
    return {
        "domains": [
            {"name": d["name"], "description": d["description"]}
            for d in get_domains(schema)
        ]
    }


# ── data-quality report (validator verdict + descriptive profile) ────────────
# Computed live over the generated CSVs and cached until they change (a cheap
# stat of ~50 small files), so opening the panel repeatedly is instant while a
# regenerate is still picked up. Read-only over the tracked CSVs — it never
# perturbs generation or the determinism guard.

_quality_cache: dict[str, Any] = {"sig": None, "payload": None}


def _data_signature(data_dir: Path) -> str:
    """A cheap fingerprint of the CSV set — names, sizes, mtimes. Changes when the
    data is regenerated, so the cached report invalidates. Empty when unreadable."""
    try:
        return "|".join(sorted(
            f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}"
            for p in data_dir.glob("*.csv")
        ))
    except OSError:
        return ""


@app.get("/api/quality")
def quality() -> dict[str, Any]:
    """Descriptive data-quality report over the generated CSVs: the validator's
    verdict (schema conformance + referential integrity) plus a per-column
    profile (completeness, cardinality, numeric spread, categorical frequency)."""
    sig = _data_signature(DATA_DIR)
    if not sig:
        return {"available": False,
                "error": "No generated data found. Run the pipeline to build the dataset first."}
    if _quality_cache["sig"] != sig:
        try:
            report = validate_dataset(DATA_DIR)
        except Exception:
            logger.exception("failed to compute the data-quality report")
            return {"available": False,
                    "error": "Could not compute the data-quality report from the generated CSVs."}
        _quality_cache["sig"] = sig
        _quality_cache["payload"] = {"available": True, **report.to_dict()}
    return _quality_cache["payload"]


# ── agent result -> UI contract ─────────────────────────────────────────────

def _last_attempted_sql(trace) -> str:
    """The most recent run_sql the agent tried, even if it errored — Step.args
    preserves the arguments on failed calls, so the UI can still show the SQL
    that broke rather than nothing."""
    for step in reversed(trace):
        if step.tool == "run_sql":
            return step.args.get("sql", "") or ""
    return ""


def _trace_payload(trace) -> list[dict]:
    out: list[dict] = []
    for s in trace:
        if s.tool == "run_sql":
            detail = s.args.get("sql", "")
        elif s.tool == "get_schema_context":
            detail = s.args.get("question", "")
        elif s.tool == "sample_values":
            detail = f"{s.args.get('table', '')}.{s.args.get('column', '')}"
        else:
            detail = ""
        out.append({
            "kind": s.kind,
            "tool": s.tool,
            "detail": detail,
            "observation": s.observation,
        })
    return out


def _failure_message(result) -> str:
    """A short, non-empty caveat for the UI when the run did not conclude with a
    data-backed answer. The agent's own words (if any) are returned separately in
    `answer`, so this is the *reason*, not a repeat of the answer.

    When a query did run, cite it (best-effort synthesis on step-exhaustion)
    instead of a bare stop line — a max_steps stop returns answer=''."""
    last = result.last_result
    if last is not None:
        rc = last.get("row_count", len(last.get("rows", [])))
        return (f"The run didn't conclude cleanly, but the last query returned {rc} row(s). "
                "Treat the answer as unverified against the data.")
    if result.stopped == "max_steps":
        steps = sum(1 for s in result.trace if s.kind == "tool")
        return f"Stopped after {steps} step(s) without reaching a conclusive, data-backed answer."
    return "The answer wasn't backed by a query result, so it couldn't be verified against the data."


# ── graceful, human-friendly failure envelopes ──────────────────────────────
# When Neo4j or Groq is unavailable we must not leak a stack trace to the UI.
# Classify the known infra failures into a small envelope the frontend can
# present cleanly (title from `error_kind`, message from `error`); the raw cause
# is logged server-side, never shown. Same envelope shape as a success so the
# client has one contract.

_KG_DOWN  = (ServiceUnavailable, SessionExpired, AuthError, ConfigurationError)
_LLM_DOWN = (APIConnectionError, APIStatusError)

_FRIENDLY = {
    "config":          "DataPulse isn't fully configured on the server. The Neo4j or Groq credentials are missing. Add them to the server's .env and restart.",
    "kg_unavailable":  "Can't reach the knowledge graph (Neo4j) right now. It may be paused or unreachable. Check the connection and try again in a moment.",
    "llm_unavailable": "Can't reach the language model (Groq) right now. It may be down, timing out, or the API key may be invalid. Please try again shortly.",
    "rate_limited":    "The language model (Groq free tier) is rate-limited right now. Wait a minute and try again.",
    "internal":        "Something went wrong while answering your question. Please try again.",
}


def _error_response(kind: str, context: dict | None = None, *, detail: str | None = None) -> dict[str, Any]:
    """A friendly, structured failure envelope. `error_kind` lets the UI pick a
    title; `error` is the human-readable message. The raw cause is logged, not shown."""
    if detail:
        logger.warning("query failed [%s]: %s", kind, detail)
    return {
        "success": False, "answer": "", "grounded": None, "grounded_reason": None,
        "sql": "", "columns": [], "rows": [],
        "schema_context": context or {}, "trace": [], "attempts": 0,
        "stopped": kind, "error_kind": kind, "error": _FRIENDLY[kind],
    }


@app.post("/api/query")
def query(req: QueryRequest) -> dict[str, Any]:
    uri      = os.getenv("NEO4J_URI")
    user     = os.getenv("NEO4J_USERNAME")
    pwd      = os.getenv("NEO4J_PASSWORD")
    api_key = os.getenv("GROQ_API_KEY")

    if not all([uri, user, pwd, api_key]):
        return _error_response("config")

    # One retrieval populates the UI's schema panel (domain badges + table pills).
    # It is the same question-level context the agent sees on its first tool call;
    # tables the agent later reaches via sub-questions may differ slightly.
    try:
        context = retrieve_schema_context(req.question, uri, user, pwd, top_k=req.top_k)
    except _KG_DOWN as exc:
        return _error_response("kg_unavailable", detail=str(exc))
    except Exception as exc:
        logger.exception("unexpected KG-retrieval error")
        return _error_response("internal", detail=str(exc))

    try:
        result = answer_question(
            req.question,
            api_key=api_key, uri=uri, user=user, password=pwd, db_path=DB_PATH,
        )
    except RateLimitExhausted as exc:
        return _error_response("rate_limited", context, detail=str(exc))
    except _LLM_DOWN as exc:
        return _error_response("llm_unavailable", context, detail=str(exc))
    except _KG_DOWN as exc:  # Neo4j dropped mid-run (agent tools)
        return _error_response("kg_unavailable", context, detail=str(exc))
    except Exception as exc:
        logger.exception("unexpected agent error")
        return _error_response("internal", context, detail=str(exc))

    last     = result.last_result or {}
    # Honest success: a conclusive final answer that actually ran SQL. `last_result
    # is not None` alone only means *some* query ran, not that the answer used it;
    # a max_steps stop (answer="") or a final answer with no SQL is not a success.
    success  = (result.stopped == "final"
                and bool(result.answer.strip())
                and result.last_result is not None)
    # Advisory grounding signal (deterministic, zero extra LLM calls): do the
    # answer's figures actually appear in the rows? Never gates success; surfaced
    # as an "unverified against data" caveat. grounded=False when no SQL backs it.
    grounding = check_grounding(result.answer, result.last_result)
    attempts = sum(1 for s in result.trace if s.tool == "run_sql")
    return {
        "success":        success,
        "answer":         result.answer,
        "grounded":       grounding["grounded"],
        "grounded_reason": grounding["reason"],
        "sql":            result.last_sql or _last_attempted_sql(result.trace),
        "columns":        last.get("columns", []),
        "rows":           last.get("rows", []),
        "schema_context": context,
        "trace":          _trace_payload(result.trace),
        "attempts":       attempts,
        "stopped":        result.stopped,
        "error":          None if success else _failure_message(result),
        "error_kind":     None if success else "no_result",
    }


# Serve vanilla JS frontend
STATIC_PATH = Path(__file__).parent.parent.parent / "frontend"
if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")

    @app.get("/")
    def root():
        return FileResponse(str(STATIC_PATH / "index.html"))
