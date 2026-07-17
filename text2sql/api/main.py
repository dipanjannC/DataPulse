"""FastAPI backend for DataPulse Text2SQL."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from text2sql.knowledge_graph.retriever import retrieve_schema_context
from text2sql.sql_gen.generator import generate_sql
from text2sql.metadata.utils import load_schema, get_domains

DB_PATH   = Path(__file__).parent.parent / "db" / "sales.db"
DIST_PATH = Path(__file__).parent.parent / "frontend" / "dist"

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


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "kg_uri": os.getenv("NEO4J_URI", "not configured"),
        "db_exists": DB_PATH.exists(),
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


@app.post("/api/query")
def query(req: QueryRequest) -> dict[str, Any]:
    uri      = os.getenv("NEO4J_URI")
    user     = os.getenv("NEO4J_USERNAME")
    pwd      = os.getenv("NEO4J_PASSWORD")
    groq_key = os.getenv("GROQ_API_KEY")

    if not all([uri, user, pwd, groq_key]):
        raise HTTPException(status_code=500, detail="Missing environment variables")

    try:
        context = retrieve_schema_context(req.question, uri, user, pwd, top_k=req.top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KG retrieval failed: {exc}")

    conn = sqlite3.connect(str(DB_PATH))
    try:
        result = generate_sql(req.question, context, groq_key, conn)
    finally:
        conn.close()

    if not result["success"]:
        return {
            "success": False,
            "error": result.get("error", "Unknown error"),
            "sql": result.get("sql", ""),
            "schema_context": context,
            "rows": [],
            "columns": [],
            "attempts": result.get("attempts", 0),
        }

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute(result["sql"])
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows    = [list(r) for r in cursor.fetchmany(500)]
        conn.close()
        return {
            "success": True,
            "sql": result["sql"],
            "schema_context": context,
            "columns": columns,
            "rows": rows,
            "attempts": result["attempts"],
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "sql": result["sql"],
            "schema_context": context,
            "rows": [],
            "columns": [],
            "attempts": result.get("attempts", 0),
        }


# Serve vanilla JS frontend
STATIC_PATH = Path(__file__).parent / "static"
if STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_PATH)), name="static")

    @app.get("/")
    def root():
        return FileResponse(str(STATIC_PATH / "index.html"))
