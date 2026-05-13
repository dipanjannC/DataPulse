"""Read-only Cypher tool exposed to the google-adk agent."""

from __future__ import annotations

import re
from typing import Any, Protocol


MAX_ROWS = 100

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(?:create|merge|delete|set|drop|remove|detach)\b|\bload\s+csv\b|\bcall\s+(?:apoc|db|dbms)\.",
    re.IGNORECASE,
)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


class _StoreLike(Protocol):
    def run_read(self, query: str, **params: Any) -> list[dict]: ...


def _strip_comments(query: str) -> str:
    return _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", query))


def _violation(query: str) -> str | None:
    stripped = _strip_comments(query)
    match = _FORBIDDEN_KEYWORDS.search(stripped)
    if match:
        return match.group(0)
    return None


def run_cypher(query: str, store: _StoreLike) -> dict[str, Any]:
    """Run a read-only Cypher query.

    Returns a dict with one of two shapes:
      - On success: {"rows": [...], "row_count": int, "truncated_at": int | None}
      - On rejection or driver error: {"error": "...", "rows": []}

    The agent should react to ``error`` by reformulating the query rather than
    crashing the run.
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "empty query", "rows": []}

    violation = _violation(query)
    if violation:
        return {
            "error": (
                f"read-only guard: keyword '{violation}' is not allowed. "
                "Only MATCH/RETURN/WITH/UNWIND read queries are permitted."
            ),
            "rows": [],
        }

    try:
        rows = store.run_read(query)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "rows": []}

    truncated_at: int | None = None
    if len(rows) > MAX_ROWS:
        truncated_at = MAX_ROWS
        rows = rows[:MAX_ROWS]
    return {"rows": rows, "row_count": len(rows), "truncated_at": truncated_at}
