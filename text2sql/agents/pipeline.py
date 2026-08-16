"""Multi-agent pipeline — streams SSE events as each agent completes.

Each agent does real work against Neo4j, SQLite, and the Groq LLM.
The generator yields newline-terminated ``data: {...}`` strings that
FastAPI's StreamingResponse forwards directly to the browser.

Usage::

    from text2sql.agents.pipeline import run_pipeline

    for chunk in run_pipeline(question, api_key=..., neo4j_uri=..., ...):
        yield chunk          # each chunk is a complete SSE event string
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Generator

from groq import Groq

from src.knowledge_graph.retriever import retrieve_schema_context
from text2sql.agent.tools import run_sql as _run_sql

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL = "llama-3.3-70b-versatile"


# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event line."""
    return f"data: {json.dumps(data, default=str)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — LEXIS  (NL Interpreter)
# ─────────────────────────────────────────────────────────────────────────────

def run_lexis(question: str, api_key: str) -> dict:
    """Parse the natural-language question into structured intent metadata."""
    t0 = time.perf_counter()

    client = Groq(api_key=api_key)
    prompt = (
        'You are a query-intent analyser for a business intelligence system.\n'
        f'Question: "{question}"\n\n'
        'Respond with ONLY valid JSON (no markdown, no prose):\n'
        '{\n'
        '  "intent": "<aggregate|list|compare|trend|lookup|filter>",\n'
        '  "primary_metric": "<main measure or null>",\n'
        '  "entities": ["<entity1>", "..."],\n'
        '  "time_reference": "<time period or null>",\n'
        '  "filters": ["<condition1>", "..."],\n'
        '  "sort_order": "<top|bottom|none>",\n'
        '  "limit": <integer or null>,\n'
        '  "confidence": <0.0–1.0>\n'
        '}'
    )

    parsed: dict[str, Any] = {}
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown code fences if the model wraps output
        raw = re.sub(r"```(?:json)?\n?", "", raw).replace("```", "").strip()
        parsed = json.loads(raw)
    except Exception as exc:
        # Heuristic fallback so the pipeline keeps going
        intent = (
            "aggregate"
            if any(w in question.lower() for w in ["total", "sum", "count", "how many", "average", "avg"])
            else "list"
        )
        parsed = {
            "intent": intent,
            "primary_metric": None,
            "entities": [],
            "time_reference": None,
            "filters": [],
            "sort_order": "none",
            "limit": None,
            "confidence": 0.6,
            "_parse_fallback": str(exc)[:120],
        }

    confidence = float(parsed.get("confidence", 0.8))
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        **parsed,
        "question": question,
        "duration_ms": duration_ms,
        "accuracy": int(min(confidence, 1.0) * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — GRAPHOS  (Knowledge-Graph Search Agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_graphos(
    question: str,
    uri: str,
    user: str,
    pwd: str,
    top_k: int = 10,
) -> dict:
    """Vector-search the Neo4j knowledge graph and return schema context."""
    t0 = time.perf_counter()

    ctx = retrieve_schema_context(question, uri, user, pwd, top_k=top_k)

    tables_dict = ctx.get("tables", {})
    joins       = ctx.get("joins",   [])
    domains     = ctx.get("domains", [])
    metrics     = ctx.get("metrics", [])

    # Summarise tables as a simple list of {name, domain, description}
    tables_list = [
        {
            "name":        name,
            "domain":      info.get("domain", ""),
            "description": info.get("description", ""),
            "col_count":   len(info.get("columns", [])),
        }
        for name, info in tables_dict.items()
    ]

    # Relevance estimate: saturates at 1.0 around 5 tables + 3 joins
    relevance = min(
        1.0,
        len(tables_list) * 0.12 + len(joins) * 0.08 + len(metrics) * 0.04 + 0.28,
    )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "tables_found":            tables_list,
        "domains_found":           domains,
        "joins_found":             joins,
        "metrics_found":           metrics,
        "cross_domain_unjoinable": ctx.get("cross_domain_unjoinable", False),
        "schema_context":          ctx,          # kept for downstream agents
        "relevance_score":         round(relevance, 2),
        "duration_ms":             duration_ms,
        "accuracy":                int(relevance * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — SCOUT  (Schema Discovery Agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_scout(question: str, graphos: dict, db_path: Path) -> dict:
    """Probe SQLite for actual column metadata; build a per-domain breakdown."""
    t0 = time.perf_counter()

    tables_list = graphos.get("tables_found", [])
    domains     = graphos.get("domains_found", [])
    joins       = graphos.get("joins_found",   [])

    # ── per-domain breakdown ──────────────────────────────────────────────────
    domain_breakdown: dict[str, list[str]] = {}
    for t in tables_list:
        d = t.get("domain") or "unknown"
        domain_breakdown.setdefault(d, []).append(t["name"])

    # ── live column discovery from SQLite ──────────────────────────────────────
    discovered: dict[str, list[dict]] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for t in tables_list[:10]:          # cap probes to avoid slowness
            tname = t.get("name", "")
            if not tname:
                continue
            try:
                rows = conn.execute(f'PRAGMA table_info("{tname}")').fetchall()
                discovered[tname] = [
                    {
                        "name":    r["name"],
                        "type":    r["type"],
                        "notnull": bool(r["notnull"]),
                        "pk":      bool(r["pk"]),
                    }
                    for r in rows
                ]
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    total_cols = sum(len(v) for v in discovered.values())
    probed     = len(discovered)
    coverage   = min(
        1.0,
        (len(tables_list) / max(1, 3)) * 0.4
        + (probed / max(1, len(tables_list))) * 0.6,
    )

    # ── domain confidence scores ────────────────────────────────────────────
    domain_scores = {
        d["name"]: round(float(d.get("score") or 0), 3)
        for d in domains
    }

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "domain_breakdown":   domain_breakdown,
        "domain_scores":      domain_scores,
        "tables_mapped":      [t["name"] for t in tables_list],
        "columns_discovered": discovered,
        "total_columns":      total_cols,
        "joins_available":    len(joins),
        "coverage_score":     round(coverage, 2),
        "duration_ms":        duration_ms,
        "accuracy":           int(coverage * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Agent 4 — FORGE  (SQL Writer Agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_forge(question: str, graphos: dict, scout: dict, api_key: str) -> dict:
    """Generate a SQLite-compatible SELECT query from schema context.

    Uses SCOUT's live column discovery so column names are exact SQLite names,
    not KG-metadata guesses that may diverge from the real DDL.
    """
    t0 = time.perf_counter()

    tables_list        = graphos.get("tables_found",   [])
    joins              = graphos.get("joins_found",    [])
    metrics            = graphos.get("metrics_found",  [])
    columns_discovered = scout.get("columns_discovered", {})   # ← from SCOUT

    # Build schema with REAL column names from SQLite PRAGMA (SCOUT's discovery)
    schema_lines = []
    for t in tables_list[:8]:
        tname = t["name"]
        cols  = columns_discovered.get(tname, [])
        if cols:
            col_str = ", ".join(
                f"{c['name']} ({c['type']})" + (" [PK]" if c.get("pk") else "")
                for c in cols
            )
            schema_lines.append(f"  - {tname} [{t.get('domain','')}] — columns: {col_str}")
        else:
            schema_lines.append(f"  - {tname} [{t.get('domain','')}]: {t.get('description','')}")

    join_lines = [
        f"  - {j['from_table']}.{j['from_column']} = {j['to_table']}.{j['to_column']}"
        for j in joins[:6]
    ]
    metric_lines = [
        f"  - {m.get('name','')}: {m.get('expression', m.get('description',''))}"
        for m in metrics[:4]
    ]

    schema_text  = "\n".join(schema_lines)  or "  (no tables retrieved)"
    join_text    = "\n".join(join_lines)    or "  (no join keys defined)"
    metric_text  = "\n".join(metric_lines)  or "  (no metric definitions)"

    client = Groq(api_key=api_key)
    prompt = (
        f'You are a SQLite expert. Write a precise read-only SQL query for this question.\n\n'
        f'Question: "{question}"\n\n'
        f'Available tables (with EXACT column names from the database):\n{schema_text}\n\n'
        f'Available join keys:\n{join_text}\n\n'
        f'Canonical metrics:\n{metric_text}\n\n'
        'CRITICAL RULES:\n'
        '- Use ONLY the exact column names listed above — do NOT invent column names\n'
        '- SQLite syntax only (strftime, not TO_DATE/EXTRACT)\n'
        '- Only SELECT or WITH…SELECT — no DML\n'
        '- Alias all aggregations (e.g. SUM(...) AS total_revenue)\n'
        '- Add LIMIT 100 if returning many rows\n'
        '- Use only tables listed above\n\n'
        'Output ONLY the SQL query. No prose, no markdown fences.'
    )

    sql       = ""
    generated = False
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=600,
        )
        sql = (resp.choices[0].message.content or "").strip()
        sql = re.sub(r"```(?:sql)?\n?", "", sql).replace("```", "").strip()
        generated = bool(sql)
    except Exception as exc:
        sql = ""
        generated = False

    complexity = _sql_complexity(sql)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "sql":         sql,
        "generated":   generated,
        "complexity":  complexity,
        "duration_ms": duration_ms,
        "accuracy":    88 if generated and sql else 0,
    }


def _sql_complexity(sql: str) -> str:
    if not sql:
        return "none"
    u = sql.upper()
    if any(w in u for w in ("WITH ", "OVER(", "OVER (", "PARTITION", "UNION")):
        return "advanced"
    if any(w in u for w in ("JOIN", "GROUP BY", "HAVING")):
        return "intermediate"
    return "simple"


# ─────────────────────────────────────────────────────────────────────────────
# Agent 5 — SENTINEL  (SQL Validator Agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_sentinel(sql: str, db_path: Path, tables_in_context: list[str]) -> dict:
    """Validate the SQL for safety, syntax, and schema alignment."""
    t0 = time.perf_counter()

    issues:   list[str] = []
    warnings: list[str] = []
    checks = {
        "safety":    False,
        "structure": False,
        "syntax":    False,
        "tables":    False,
    }

    if not sql.strip():
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "valid":       False,
            "issues":      ["FORGE produced no SQL"],
            "warnings":    [],
            "checks":      checks,
            "score":       0.0,
            "duration_ms": duration_ms,
            "accuracy":    0,
        }

    # ── 1. Safety: only SELECT / WITH allowed ─────────────────────────────────
    first = re.split(r"\s+", sql.strip().lstrip(";").strip(), maxsplit=1)[0].upper()
    if first in ("SELECT", "WITH"):
        checks["safety"] = True
    else:
        issues.append(f"Safety — only SELECT/WITH allowed (got {first!r})")

    # ── 2. Structure: contains SELECT ────────────────────────────────────────
    if "SELECT" in sql.upper():
        checks["structure"] = True
    else:
        issues.append("Structure — query does not contain SELECT")

    # ── 3. Syntax: EXPLAIN via SQLite ────────────────────────────────────────
    if checks["safety"]:
        try:
            conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
            conn.execute(f"EXPLAIN {sql}")
            conn.close()
            checks["syntax"] = True
        except sqlite3.OperationalError as exc:
            issues.append(f"Syntax — {exc}")
        except Exception as exc:
            warnings.append(f"Syntax check skipped: {exc}")

    # ── 4. Tables: referenced tables exist in the KG context ─────────────────
    mentioned = set()
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE):
        mentioned.add(m.group(1).lower())
    ctx_lower = {t.lower() for t in tables_in_context}
    missing   = [t for t in mentioned if t not in ctx_lower]
    if missing:
        warnings.append(f"Tables not in KG context: {', '.join(missing)}")
    else:
        checks["tables"] = True

    valid = checks["safety"] and checks["syntax"] and checks["structure"]
    score = sum(checks.values()) / len(checks)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "valid":       valid,
        "issues":      issues,
        "warnings":    warnings,
        "checks":      checks,
        "score":       round(score, 2),
        "duration_ms": duration_ms,
        "accuracy":    int(score * 100),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SQL auto-correction helper (used by ORACLE on first-attempt failure)
# ─────────────────────────────────────────────────────────────────────────────

def _get_actual_schema(db_path: Path, tables: list[str]) -> str:
    """Return a compact DDL-like schema string for the given tables."""
    lines: list[str] = []
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        for tname in tables:
            try:
                cols = conn.execute(f'PRAGMA table_info("{tname}")').fetchall()
                col_str = ", ".join(
                    c["name"] + " " + c["type"] + (" PK" if c["pk"] else "")
                    for c in cols
                )
                lines.append(f"  {tname}({col_str})")
            except Exception:
                pass
        conn.close()
    except Exception:
        pass
    return "\n".join(lines) or "  (schema unavailable)"


def _fix_sql(sql: str, error: str, db_path: Path, api_key: str, question: str) -> str:
    """Ask Groq to repair a failing SQL query given the SQLite error and real schema."""
    # Extract table names mentioned in the SQL to fetch their real schema
    mentioned = re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE)
    real_schema = _get_actual_schema(db_path, list(dict.fromkeys(mentioned)))

    try:
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f'The following SQLite query failed with error: "{error}"\n\n'
                    f'Failing SQL:\n{sql}\n\n'
                    f'Actual table schemas (exact column names):\n{real_schema}\n\n'
                    f'Original question: "{question}"\n\n'
                    'Fix the SQL so it uses only the exact column names listed above. '
                    'Output ONLY the corrected SQL query. No prose, no markdown fences.'
                ),
            }],
            temperature=0.0,
            max_tokens=500,
        )
        fixed = (resp.choices[0].message.content or "").strip()
        fixed = re.sub(r"```(?:sql)?\n?", "", fixed).replace("```", "").strip()
        return fixed
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Agent 6 — ORACLE  (Executor & Natural-Language Response Agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_oracle(
    question: str,
    sql:      str,
    db_path:  Path,
    api_key:  str,
    sentinel_valid: bool,   # informational only — ORACLE always attempts execution  # noqa: ARG001
) -> dict:
    """Execute the SQL and translate the result into a natural-language answer.

    ORACLE always attempts execution even when SENTINEL flagged a warning — the
    real SQLite error (if any) is reported back directly.  Only an empty SQL
    string stops execution.
    """
    t0 = time.perf_counter()

    if not sql.strip():
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "executed":    False,
            "rows":        [],
            "columns":     [],
            "row_count":   0,
            "answer":      "FORGE produced no SQL — try rephrasing the question.",
            "grounded":    False,
            "duration_ms": duration_ms,
            "accuracy":    0,
        }

    # ── Execute (with one auto-correction retry) ──────────────────────────────
    exec_result = _run_sql(sql, db_path)
    sql_error   = exec_result.get("error")

    # If SQLite raised an error (e.g. bad column name from FORGE), ask the LLM
    # to fix the SQL using the real schema and retry once.
    if sql_error:
        fixed = _fix_sql(sql, sql_error, db_path, api_key, question)
        if fixed and fixed != sql:
            retry = _run_sql(fixed, db_path)
            if not retry.get("error"):
                sql        = fixed        # show the corrected SQL downstream
                exec_result = retry
                sql_error   = None

    if sql_error:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "executed":    False,
            "rows":        [],
            "columns":     [],
            "row_count":   0,
            "answer":      f"The SQL query failed: {sql_error}",
            "grounded":    False,
            "sql_error":   sql_error,
            "duration_ms": duration_ms,
            "accuracy":    15,
        }

    rows      = exec_result.get("rows",     [])
    columns   = exec_result.get("columns",  [])
    row_count = exec_result.get("row_count", len(rows))

    # ── Translate to natural language ─────────────────────────────────────────
    preview  = rows[:5]
    data_str = json.dumps({"columns": columns, "rows": preview}, default=str)

    answer = ""
    try:
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": (
                    f'Question: "{question}"\n\n'
                    f'SQL result ({row_count} row(s) total; first {len(preview)} shown):\n'
                    f'{data_str}\n\n'
                    'Write a clear, concise 1–3 sentence natural-language answer. '
                    'Be specific — include the actual numbers from the result. '
                    'If no rows, say no matching data was found.\n'
                    'Answer:'
                ),
            }],
            temperature=0.2,
            max_tokens=220,
        )
        answer = (resp.choices[0].message.content or "").strip()
    except Exception:
        # Graceful fallback
        if row_count == 0:
            answer = "No data found matching your query."
        elif row_count == 1 and len(columns) == 1:
            answer = f"Result: {rows[0][0]}"
        else:
            first = dict(zip(columns, rows[0])) if rows else {}
            answer = f"Found {row_count} result(s). Top entry: {first}."

    grounded    = row_count > 0
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "executed":    True,
        "rows":        rows,
        "columns":     columns,
        "row_count":   row_count,
        "answer":      answer,
        "grounded":    grounded,
        "duration_ms": duration_ms,
        "accuracy":    95 if grounded else 55,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator — streams SSE events
# ─────────────────────────────────────────────────────────────────────────────

AGENT_META = {
    "LEXIS":    {"role": "NL Interpreter",     "icon": "◈", "color": "#A100FF"},
    "GRAPHOS":  {"role": "KG Search Agent",    "icon": "◉", "color": "#7EC8FF"},
    "SCOUT":    {"role": "Schema Discovery",   "icon": "◎", "color": "#BE82FF"},
    "FORGE":    {"role": "SQL Writer",         "icon": "◆", "color": "#7DD6C0"},
    "SENTINEL": {"role": "SQL Validator",      "icon": "◈", "color": "#F0A868"},
    "ORACLE":   {"role": "Executor & NL Agent","icon": "◉", "color": "#A100FF"},
}


def run_pipeline(
    question: str,
    *,
    api_key:   str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_pwd:  str,
    db_path:   Path,
    top_k:     int = 10,
) -> Generator[str, None, None]:
    """Run the six-agent pipeline, yielding SSE event strings.

    Each agent emits two events:
      ``{"agent": NAME, "status": "active",  "message": "..."}``
      ``{"agent": NAME, "status": "done"|"error", "result": {...}, "accuracy": N}``

    A final ``{"status": "complete", ...}`` event carries the consolidated answer.
    """
    t_pipeline = time.perf_counter()
    results: dict[str, dict] = {}

    def _emit(agent: str, status: str, **kw) -> str:
        return _sse({"agent": agent, "status": status, "meta": AGENT_META.get(agent, {}), **kw})

    # ── LEXIS ─────────────────────────────────────────────────────────────────
    yield _emit("LEXIS", "active", message="Parsing your question and extracting intent…")
    try:
        results["lexis"] = run_lexis(question, api_key)
        yield _emit("LEXIS", "done",
                    result=results["lexis"],
                    accuracy=results["lexis"]["accuracy"])
    except Exception as exc:
        yield _emit("LEXIS", "error", error=str(exc)[:200], accuracy=0)
        results["lexis"] = {"accuracy": 0, "intent": "unknown", "entities": [], "filters": []}

    # ── GRAPHOS ───────────────────────────────────────────────────────────────
    yield _emit("GRAPHOS", "active", message="Searching the knowledge graph…")
    try:
        results["graphos"] = run_graphos(question, neo4j_uri, neo4j_user, neo4j_pwd, top_k)
        yield _emit("GRAPHOS", "done",
                    result=results["graphos"],
                    accuracy=results["graphos"]["accuracy"])
    except Exception as exc:
        yield _emit("GRAPHOS", "error", error=str(exc)[:200], accuracy=0)
        results["graphos"] = {
            "accuracy": 0, "tables_found": [], "joins_found": [],
            "metrics_found": [], "domains_found": [], "schema_context": {},
        }

    # ── SCOUT ─────────────────────────────────────────────────────────────────
    yield _emit("SCOUT", "active", message="Discovering tables, columns and domains…")
    try:
        results["scout"] = run_scout(question, results["graphos"], db_path)
        yield _emit("SCOUT", "done",
                    result=results["scout"],
                    accuracy=results["scout"]["accuracy"])
    except Exception as exc:
        yield _emit("SCOUT", "error", error=str(exc)[:200], accuracy=0)
        results["scout"] = {"accuracy": 0, "tables_mapped": [], "columns_discovered": {}}

    # ── FORGE ─────────────────────────────────────────────────────────────────
    yield _emit("FORGE", "active", message="Writing the SQL query…")
    try:
        results["forge"] = run_forge(question, results["graphos"], results["scout"], api_key)
        yield _emit("FORGE", "done",
                    result=results["forge"],
                    accuracy=results["forge"]["accuracy"])
    except Exception as exc:
        yield _emit("FORGE", "error", error=str(exc)[:200], accuracy=0)
        results["forge"] = {"accuracy": 0, "sql": "", "generated": False, "complexity": "none"}

    # ── SENTINEL ──────────────────────────────────────────────────────────────
    yield _emit("SENTINEL", "active", message="Validating SQL — safety, syntax, schema alignment…")
    tables_in_ctx = [t["name"] for t in results["graphos"].get("tables_found", [])]
    try:
        results["sentinel"] = run_sentinel(
            results["forge"].get("sql", ""), db_path, tables_in_ctx
        )
        yield _emit("SENTINEL", "done",
                    result=results["sentinel"],
                    accuracy=results["sentinel"]["accuracy"])
    except Exception as exc:
        yield _emit("SENTINEL", "error", error=str(exc)[:200], accuracy=0)
        results["sentinel"] = {"accuracy": 0, "valid": False, "issues": [str(exc)], "warnings": []}

    # ── ORACLE ────────────────────────────────────────────────────────────────
    yield _emit("ORACLE", "active", message="Executing query and translating result to plain English…")
    try:
        results["oracle"] = run_oracle(
            question,
            results["forge"].get("sql", ""),
            db_path,
            api_key,
            sentinel_valid=results["sentinel"].get("valid", False),
        )
        yield _emit("ORACLE", "done",
                    result=results["oracle"],
                    accuracy=results["oracle"]["accuracy"])
    except Exception as exc:
        yield _emit("ORACLE", "error", error=str(exc)[:200], accuracy=0)
        results["oracle"] = {
            "accuracy": 0, "answer": str(exc), "executed": False,
            "rows": [], "columns": [], "row_count": 0,
        }

    # ── Final summary ──────────────────────────────────────────────────────────
    total_ms     = int((time.perf_counter() - t_pipeline) * 1000)
    agent_keys   = ["lexis", "graphos", "scout", "forge", "sentinel", "oracle"]
    avg_accuracy = int(
        sum(results.get(k, {}).get("accuracy", 0) for k in agent_keys) / len(agent_keys)
    )

    yield _sse({
        "status":       "complete",
        "total_ms":     total_ms,
        "avg_accuracy": avg_accuracy,
        "question":     question,
        "answer":       results.get("oracle", {}).get("answer", ""),
        "sql":          results.get("forge",  {}).get("sql",    ""),
        "rows":         results.get("oracle", {}).get("rows",   []),
        "columns":      results.get("oracle", {}).get("columns",[]),
        "row_count":    results.get("oracle", {}).get("row_count", 0),
        "agents": {
            k: {
                "accuracy":    results.get(k, {}).get("accuracy", 0),
                "duration_ms": results.get(k, {}).get("duration_ms", 0),
            }
            for k in agent_keys
        },
    })
