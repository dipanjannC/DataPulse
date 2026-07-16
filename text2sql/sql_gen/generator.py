"""Step 7 — SQL generator via Groq API.

Accepts a natural-language question and the schema context returned by the
KG retriever.  Calls the Groq LLM, extracts the SQL, validates it against
the local SQLite database, and retries (up to MAX_RETRIES) on parse errors.
"""
from __future__ import annotations

import re
import sqlite3

from groq import Groq

MODEL       = "llama-3.3-70b-versatile"
MAX_RETRIES = 3

_SYSTEM_PROMPT = """\
You are an expert SQLite query writer.

Rules:
- Output ONLY the raw SQL query — no markdown fences, no explanation, nothing else.
- Use table and column names exactly as shown in the schema below.
- Use JOINs whenever data from multiple tables is needed.
- Default LIMIT is 100 rows unless the user specifies otherwise.
- Never use DROP, DELETE, UPDATE, INSERT, CREATE, ALTER, or any DDL / DML statement.
"""


# ── public API ────────────────────────────────────────────────────────────────

def generate_sql(
    question: str,
    context: dict,
    api_key: str,
    db_conn: sqlite3.Connection | None = None,
) -> dict:
    """
    Generate and (optionally) validate SQL.

    Returns:
        {
          "sql":      str,
          "success":  bool,
          "error":    str | None,
          "attempts": int,
        }
    """
    client       = Groq(api_key=api_key)
    schema_block = _format_schema(context)
    user_message = f"{schema_block}\n\n## Question\n{question}"

    last_sql: str   = ""
    last_error: str = ""

    for attempt in range(1, MAX_RETRIES + 1):
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        if attempt == 1:
            messages.append({"role": "user", "content": user_message})
        else:
            messages += [
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": last_sql},
                {"role": "user",      "content": (
                    f"That SQL produced an error: {last_error}\n"
                    "Fix the SQL and return only the corrected query."
                )},
            ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1,
        )
        raw_output = response.choices[0].message.content.strip()
        sql        = _extract_sql(raw_output)

        if db_conn is not None:
            ok, err = _validate(sql, db_conn)
            if ok:
                return {"sql": sql, "success": True, "error": None, "attempts": attempt}
            last_sql, last_error = sql, err
        else:
            return {"sql": sql, "success": True, "error": None, "attempts": attempt}

    return {"sql": last_sql, "success": False, "error": last_error, "attempts": MAX_RETRIES}


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_schema(context: dict) -> str:
    lines = ["## Schema\n"]
    for table_name, info in context["tables"].items():
        lines.append(f"### {table_name}")
        lines.append(f"{info['description']}\n")
        lines.append("| Column | Type | PK | Description |")
        lines.append("|--------|------|----|-------------|")
        for col in info["columns"]:
            pk = "Yes" if col.get("is_pk") else ""
            lines.append(f"| {col['name']} | {col['type']} | {pk} | {col['description']} |")
        lines.append("")
    return "\n".join(lines)


def _extract_sql(text: str) -> str:
    """Strip markdown fences if the model added them anyway."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def _validate(sql: str, conn: sqlite3.Connection) -> tuple[bool, str]:
    try:
        conn.execute(f"EXPLAIN QUERY PLAN {sql}")
        return True, ""
    except sqlite3.Error as exc:
        return False, str(exc)
