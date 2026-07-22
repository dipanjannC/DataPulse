"""Tests for the SQL-planning agent: the read-only guard and the loop mechanics.

The loop is driven by a scripted fake model and fake tools, so iteration, trace
accumulation, tool-error recovery, and the step cap are all exercised with no
live Groq/Neo4j/SQLite.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from text2sql.agent.agent import (
    LLMResponse,
    RateLimitExhausted,
    Step,
    ToolCall,
    _next_wait,
    _retry_after_seconds,
    run_agent,
)
from text2sql.agent.tools import read_only_violation


# ── read-only guard ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "SELECT * FROM customers",
    "   select count(*) from orders",
    "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
    "SELECT status FROM orders -- trailing comment\n",
    "SELECT 1;",  # single trailing semicolon is fine
])
def test_guard_allows_read_queries(sql):
    assert read_only_violation(sql) is None


@pytest.mark.parametrize("sql,fragment", [
    ("DELETE FROM customers",              "only SELECT"),
    ("DROP TABLE orders",                  "only SELECT"),
    ("UPDATE customers SET is_active = 0", "only SELECT"),
    ("INSERT INTO t VALUES (1)",           "only SELECT"),
    ("ATTACH DATABASE 'x' AS y",           "only SELECT"),
    ("SELECT 1; DROP TABLE orders",        "multiple statements"),
    ("SELECT * FROM t; SELECT * FROM u",   "multiple statements"),
    ("",                                   "empty"),
    ("   ",                                "empty"),
])
def test_guard_rejects_unsafe(sql, fragment):
    violation = read_only_violation(sql)
    assert violation is not None
    assert fragment in violation


def test_guard_catches_write_hidden_after_select_keyword():
    # a CTE that then tries a write-ish keyword is still rejected
    assert read_only_violation("WITH x AS (SELECT 1) DELETE FROM t") is not None


# ── loop mechanics (scripted fake model) ────────────────────────────────────

class _ScriptedLLM:
    """Returns pre-scripted LLMResponses in order; records how many turns ran."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.turns = 0

    def __call__(self, messages, tool_schemas):
        self.turns += 1
        return self._responses.pop(0)


def test_agent_loops_tools_then_answers():
    llm = _ScriptedLLM([
        LLMResponse(None, [ToolCall("c1", "get_schema_context", {"question": "revenue"})]),
        LLMResponse(None, [ToolCall("c2", "run_sql", {"sql": "SELECT SUM(line_total) FROM order_items"})]),
        LLMResponse("Total revenue is 7,782,964.89.", []),
    ])
    tool_fns = {
        "get_schema_context": lambda question, top_k=10: {"tables": ["order_items"], "metrics": ["total revenue"]},
        "run_sql": lambda sql: {"columns": ["r"], "rows": [[7782964.89]], "row_count": 1, "truncated": False},
    }

    result = run_agent("total revenue?", llm_fn=llm, tool_fns=tool_fns)

    assert result.stopped == "final"
    assert "7,782,964.89" in result.answer
    assert [s.tool for s in result.trace] == ["get_schema_context", "run_sql", None]
    assert result.trace[-1].kind == "final"
    # the successful query + its result are captured for evaluation
    assert result.last_sql == "SELECT SUM(line_total) FROM order_items"
    assert result.last_result["rows"] == [[7782964.89]]


def test_agent_recovers_from_tool_error():
    llm = _ScriptedLLM([
        LLMResponse(None, [ToolCall("c1", "run_sql", {"sql": "DELETE FROM t"})]),
        LLMResponse(None, [ToolCall("c2", "run_sql", {"sql": "SELECT 1"})]),
        LLMResponse("done", []),
    ])

    def run_sql(sql):
        if read_only_violation(sql):
            return {"error": "read-only guard: only SELECT", "rows": []}
        return {"columns": ["n"], "rows": [[1]], "row_count": 1, "truncated": False}

    result = run_agent("q", llm_fn=llm, tool_fns={"run_sql": run_sql})

    assert result.stopped == "final"
    assert any(s.observation.startswith("error") for s in result.trace)
    # only the successful query is recorded as the last result
    assert result.last_sql == "SELECT 1"


def test_agent_handles_unknown_tool_without_crashing():
    llm = _ScriptedLLM([
        LLMResponse(None, [ToolCall("c1", "frobnicate", {})]),
        LLMResponse("recovered", []),
    ])
    result = run_agent("q", llm_fn=llm, tool_fns={})
    assert result.stopped == "final"
    assert any("unknown tool" in s.observation for s in result.trace)


def test_agent_stops_at_max_steps():
    class _AlwaysCallsTool:
        def __call__(self, messages, tool_schemas):
            return LLMResponse(None, [ToolCall("c", "run_sql", {"sql": "SELECT 1"})])

    tool_fns = {"run_sql": lambda sql: {"columns": ["n"], "rows": [[1]], "row_count": 1}}
    result = run_agent("q", llm_fn=_AlwaysCallsTool(), tool_fns=tool_fns, max_steps=3)

    assert result.stopped == "max_steps"
    assert sum(1 for s in result.trace if s.kind == "tool") == 3
    assert result.trace[-1].kind == "stopped"


# ── rate-limit waiting logic ────────────────────────────────────────────────

def _exc(headers=None, message=""):
    resp = SimpleNamespace(headers=headers) if headers is not None else None
    return SimpleNamespace(response=resp, message=message)


def test_retry_after_prefers_header():
    assert _retry_after_seconds(_exc(headers={"retry-after": "7"})) == 7.0


def test_retry_after_falls_back_to_message():
    assert _retry_after_seconds(_exc(headers={}, message="Please try again in 12.5s")) == 12.5


def test_retry_after_none_when_unknown():
    assert _retry_after_seconds(_exc(message="no timing here")) is None


def test_next_wait_transient_returns_delay():
    assert _next_wait(0.0, 8.0) == 8.0
    assert _next_wait(0.0, None) == 2.0            # conservative default


def test_next_wait_raises_on_sustained_quota():
    # a single wait longer than the per-call budget => daily quota, fail fast
    with pytest.raises(RateLimitExhausted):
        _next_wait(0.0, 120.0, max_wait=60.0)
    # cumulative waits crossing the budget also fail fast rather than block on
    with pytest.raises(RateLimitExhausted):
        _next_wait(55.0, 8.0, max_wait=60.0)
