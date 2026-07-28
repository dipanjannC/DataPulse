"""Read-only tools the SQL-planning agent can call.

Every tool is side-effect free and returns a plain dict (JSON-serialisable) so
it can be fed straight back to the model. `run_sql` is the only one that touches
data, and it is guarded three ways: a SELECT/WITH allowlist, a read-only SQLite
connection (writes fail at the engine level), and a statement timeout + row cap.
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from src.embeddings.embed import embed_query
from src.knowledge_graph.retriever import retrieve_context
from src.metadata.utils import get_all_tables, load_schema

MAX_ROWS   = 200
TIMEOUT_S  = 5.0

_LINE_COMMENT  = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b(?:insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)


# ── read-only guard ─────────────────────────────────────────────────────────

def _strip_comments(sql: str) -> str:
    return _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", sql))


def read_only_violation(sql: str) -> str | None:
    """Return a reason string if the SQL is not a safe single read query, else None."""
    if not isinstance(sql, str) or not sql.strip():
        return "empty query"
    s = _strip_comments(sql).strip().rstrip(";").strip()
    if not s:
        return "empty query"
    if ";" in s:
        return "multiple statements are not allowed"
    if not re.match(r"(?is)^(?:select|with)\b", s):
        return "only SELECT / WITH read queries are allowed"
    match = _FORBIDDEN.search(s)
    if match:
        return f"forbidden keyword '{match.group(0)}'"
    return None


def _install_timeout(conn: sqlite3.Connection, seconds: float) -> None:
    start = time.monotonic()

    def _abort_if_slow() -> int:
        return 1 if (time.monotonic() - start) > seconds else 0

    conn.set_progress_handler(_abort_if_slow, 20_000)


# ── tools ─────────────────────────────────────────────────────────────────────

def run_sql(sql: str, db_path: str | Path, max_rows: int = MAX_ROWS,
            timeout_s: float = TIMEOUT_S) -> dict:
    """Execute a read-only SELECT/WITH query against the SQLite database.

    Returns {"columns", "rows", "row_count", "truncated"} on success or
    {"error", ...} on rejection / failure.
    """
    violation = read_only_violation(sql)
    if violation:
        return {"error": f"read-only guard: {violation}", "columns": [], "rows": []}

    try:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"error": f"cannot open db read-only: {exc}", "columns": [], "rows": []}

    try:
        _install_timeout(conn, timeout_s)
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchmany(max_rows + 1)]
    except sqlite3.Error as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "columns": [], "rows": []}
    finally:
        conn.close()

    truncated = len(rows) > max_rows
    return {
        "columns": columns,
        "rows": rows[:max_rows],
        "row_count": min(len(rows), max_rows),
        "truncated": truncated,
    }


def get_schema_context(question: str, graph, top_k: int = 10) -> dict:
    """Retrieve the relevant tables, join paths, and canonical metric definitions
    for a question. Returns a ready-to-read schema block plus a short summary."""
    ctx = retrieve_context(graph, embed_query(question), top_k)
    return {
        "schema": _format_schema(ctx),
        "tables": sorted(ctx["tables"]),
        "join_count": len(ctx.get("joins", [])),
        "metrics": [m["name"] for m in ctx.get("metrics", [])],
    }


def _format_schema(context: dict) -> str:
    tables = context.get("tables", {})
    lines: list[str] = ["## Schema"]

    # Group tables by domain (single unlabelled group if domain is absent).
    by_domain: dict[str, list[str]] = {}
    for tname, info in tables.items():
        by_domain.setdefault(info.get("domain") or "", []).append(tname)

    for domain, tnames in by_domain.items():
        if domain:
            lines.append(f"\n### Domain: {domain}")
        for tname in tnames:
            info = tables[tname]
            lines.append(f"\n#### {tname}")
            if info.get("description"):
                lines.append(info["description"])
            lines.append("| Column | Type | PK | Description |")
            lines.append("|--------|------|----|-------------|")
            for col in info["columns"]:
                pk = "Yes" if col.get("is_pk") else ""
                lines.append(f"| {col['name']} | {col['type']} | {pk} | {col['description']} |")

    joins = context.get("joins") or []
    if joins:
        lines.append("\n## Join Paths")
        lines.append("Use these exact keys when joining tables:")
        for j in joins:
            lines.append(
                f"- {j['from_table']}.{j['from_column']} = {j['to_table']}.{j['to_column']}"
            )

    metrics = context.get("metrics") or []
    if metrics:
        lines.append("\n## Metric definitions")
        lines.append("When the question asks for one of these business measures, use the exact expression:")
        for m in metrics:
            lines.append(f"- {m['name']}: {m['expression']}")
            if m.get("description"):
                lines.append(f"    ({m['description']})")

    return "\n".join(lines)


def _valid_identifiers(schema: dict | None = None) -> dict[str, set[str]]:
    schema = schema or load_schema()
    return {t["name"]: {c["name"] for c in t["columns"]} for t in get_all_tables(schema)}


def sample_values(table: str, column: str, db_path: str | Path, limit: int = 20,
                  schema: dict | None = None) -> dict:
    """Return up to `limit` distinct non-null values of a column, so the agent can
    resolve a categorical filter by looking rather than guessing."""
    valid = _valid_identifiers(schema)
    if table not in valid:
        return {"error": f"unknown table '{table}'", "values": []}
    if column not in valid[table]:
        return {"error": f"unknown column '{table}.{column}'", "values": []}

    # identifiers are validated against the schema above, so quoting is safe
    sql = f'SELECT DISTINCT "{column}" AS v FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT {int(limit)}'
    result = run_sql(sql, db_path, max_rows=limit)
    if "error" in result:
        return {"error": result["error"], "values": []}
    return {"values": [r[0] for r in result["rows"]]}
