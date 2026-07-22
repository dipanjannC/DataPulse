"""FastAPI backend for DataPulse Text2SQL.

The `/api/query` endpoint routes through the multi-step tool-calling agent
(`text2sql.agent.answer_question`): the model discovers schema, resolves
categorical filters, and runs read-only SQL by *calling tools* over the
knowledge graph, so the response carries an explicit reasoning `trace` and a
natural-language `answer` alongside the SQL and rows.

The single-shot `generate_sql` path is left in the tree as a dormant fallback
(it is no longer called from here) in case the agent gets rate-limited during a
live demo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pydantic import BaseModel
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from text2sql.agent.agent import RateLimitExhausted, answer_question
from text2sql.knowledge_graph.retriever import retrieve_schema_context
from text2sql.metadata.utils import get_domains, load_schema

DB_PATH = Path(__file__).parent.parent / "db" / "sales.db"

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


def _neo4j_reachable(uri: str | None, user: str | None, pwd: str | None) -> bool:
    if not all([uri, user, pwd]):
        return False
    driver = None
    try:
        driver = GraphDatabase.driver(
            uri, auth=(user, pwd),
            connection_timeout=_HEALTH_TIMEOUT_S,
            connection_acquisition_timeout=_HEALTH_TIMEOUT_S,
        )
        driver.verify_connectivity()
        return True
    except Exception:
        return False
    finally:
        if driver is not None:
            driver.close()


@app.get("/api/health")
def health():
    uri = os.getenv("NEO4J_URI")
    kg_connected = _neo4j_reachable(uri, os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    db_exists = DB_PATH.exists()
    return {
        "status": "ok" if (kg_connected and db_exists) else "degraded",
        "kg_uri": uri or "not configured",
        "kg_connected": kg_connected,
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
    """A non-empty error for the UI: the agent's own words if it gave any, else
    a stop-reason line (a max_steps stop returns answer='')."""
    if result.answer.strip():
        return result.answer.strip()
    steps = sum(1 for s in result.trace if s.kind == "tool")
    return f"Stopped after {steps} step(s) without a conclusive result."


@app.post("/api/query")
def query(req: QueryRequest) -> dict[str, Any]:
    uri      = os.getenv("NEO4J_URI")
    user     = os.getenv("NEO4J_USERNAME")
    pwd      = os.getenv("NEO4J_PASSWORD")
    groq_key = os.getenv("GROQ_API_KEY")

    if not all([uri, user, pwd, groq_key]):
        raise HTTPException(status_code=500, detail="Missing environment variables")

    # One retrieval populates the UI's schema panel (domain badges + table pills).
    # It is the same question-level context the agent sees on its first tool call;
    # tables the agent later reaches via sub-questions may differ slightly.
    try:
        context = retrieve_schema_context(req.question, uri, user, pwd, top_k=req.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KG retrieval failed: {exc}")

    try:
        result = answer_question(
            req.question,
            groq_key=groq_key, uri=uri, user=user, password=pwd, db_path=DB_PATH,
        )
    except RateLimitExhausted as exc:
        # A daily/token quota, not a transient blip — surface it cleanly.
        return {
            "success": False, "answer": "", "sql": "",
            "columns": [], "rows": [], "schema_context": context,
            "trace": [], "attempts": 0, "stopped": "rate_limited",
            "error": str(exc),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent run failed: {exc}")

    last     = result.last_result or {}
    success  = result.last_result is not None
    attempts = sum(1 for s in result.trace if s.tool == "run_sql")
    return {
        "success":        success,
        "answer":         result.answer,
        "sql":            result.last_sql or _last_attempted_sql(result.trace),
        "columns":        last.get("columns", []),
        "rows":           last.get("rows", []),
        "schema_context": context,
        "trace":          _trace_payload(result.trace),
        "attempts":       attempts,
        "stopped":        result.stopped,
        "error":          None if success else _failure_message(result),
    }


# Serve vanilla JS frontend
STATIC_PATH = ROOT / "frontend"
if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")

    @app.get("/")
    def root():
        return FileResponse(str(STATIC_PATH / "index.html"))
