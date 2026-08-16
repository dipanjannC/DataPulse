"""A small tool-calling agent that plans NL -> SQL over the knowledge graph.

The loop is deliberately dependency-injected: `run_agent` takes an `llm_fn`
(messages, tool_schemas) -> LLMResponse and a `tool_fns` registry, so the
iteration / trace / guard logic is unit-tested with a scripted fake model and
fake tools — no live Gemini/Neo4j/SQLite. `answer_question` wires the real
Gemini client (via OpenAI-compatible endpoint) and the KG-backed tools.

The KG earns its keep here as the tool substrate: the model discovers schema,
join paths, and canonical metrics by *calling tools*, so the reasoning is an
explicit, inspectable trace rather than a single opaque generation.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from text2sql.agent import tools as _tools
from text2sql.agent.prompt import build_system_prompt
from src.knowledge_graph.retriever import _get_graph
from src.metadata.utils import get_domains, load_schema

# Gemini 2.0 Flash via Google's OpenAI-compatible endpoint.
# Free tier: 1,500 req/day, 1M tokens/day — no credit card needed.
MODEL     = "gemini-2.0-flash"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_STEPS = 6

# A transient per-minute limit clears in seconds; if honoring Retry-After would
# blow past this budget it's a sustained/daily quota, and blocking is pointless.
MAX_WAIT_PER_CALL_S = 60.0


class RateLimitExhausted(RuntimeError):
    """Raised when a rate limit won't clear within the per-call wait budget —
    i.e. a daily/token quota rather than a transient blip. Callers (e.g. a batch
    eval) should checkpoint and resume later rather than keep hammering."""


# ── normalised model I/O (both the fake and the Groq wrapper produce these) ─────

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class Step:
    kind: str                 # "tool" | "final" | "stopped"
    tool: str | None
    args: dict
    observation: str          # short, human-readable summary for the trace


@dataclass
class AgentResult:
    answer: str
    trace: list[Step]
    stopped: str              # "final" | "max_steps"
    last_sql: str | None = None
    last_result: dict | None = None


# The system-prompt template (with its {domains} marker) is configured OUTSIDE
# this module so it can be tuned per deployment / business standards without a
# code change — see text2sql/agent/prompt.py (bundled default:
# prompts/system_prompt.txt; overridable via the DATAPULSE_SYSTEM_PROMPT_PATH env
# var). build_system_prompt is imported above and re-exported here so existing
# importers keep working.


# Generic default for run_agent's default param (the fake-LLM tests hit this).
# The real path (answer_question) injects the schema-derived domain list.
SYSTEM_PROMPT = build_system_prompt([])

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema_context",
            "description": "Relevant tables, join keys, and canonical metric definitions for a question. Call first.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "The user's question, or a focused sub-question."}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_values",
            "description": "Up to 20 distinct non-null values of a column, to resolve a categorical filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table":  {"type": "string"},
                    "column": {"type": "string"},
                },
                "required": ["table", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Execute a read-only SELECT/WITH query against the SQLite database and return rows.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    },
]


# ── the loop (pure over llm_fn + tool_fns) ──────────────────────────────────────

def run_agent(
    question: str,
    *,
    llm_fn,
    tool_fns: dict,
    tool_schemas: list | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    tool_schemas = tool_schemas if tool_schemas is not None else TOOL_SCHEMAS
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    trace: list[Step] = []
    last_sql: str | None = None
    last_result: dict | None = None

    for _ in range(max_steps):
        resp = llm_fn(messages, tool_schemas)

        if not resp.tool_calls:
            answer = (resp.content or "").strip()
            trace.append(Step("final", None, {}, answer[:500]))
            return AgentResult(answer, trace, "final", last_sql, last_result)

        messages.append(_assistant_message(resp))
        for call in resp.tool_calls:
            fn = tool_fns.get(call.name)
            if fn is None:
                result = {"error": f"unknown tool '{call.name}'"}
            else:
                try:
                    result = fn(**call.arguments)
                except Exception as exc:  # a tool bug must not crash the run
                    result = {"error": f"{type(exc).__name__}: {exc}"}

            if call.name == "run_sql" and "error" not in result:
                last_sql = call.arguments.get("sql")
                last_result = result

            trace.append(Step("tool", call.name, call.arguments, _summarize(call.name, result)))
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

    trace.append(Step("stopped", None, {}, f"hit max_steps={max_steps}"))
    return AgentResult("", trace, "max_steps", last_sql, last_result)


def _assistant_message(resp: LLMResponse) -> dict:
    return {
        "role": "assistant",
        "content": resp.content or None,
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in resp.tool_calls
        ],
    }


def _summarize(tool: str, result: dict) -> str:
    if isinstance(result, dict) and result.get("error"):
        return f"error: {result['error']}"
    if tool == "run_sql":
        preview = result.get("rows", [])[:1]
        return f"{result.get('row_count', 0)} rows, columns={result.get('columns', [])}, first={preview}"
    if tool == "get_schema_context":
        return f"tables={result.get('tables', [])}, metrics={result.get('metrics', [])}"
    if tool == "sample_values":
        return f"values={result.get('values', [])}"
    return str(result)[:200]


# ── real wiring (Gemini + KG-backed tools) ──────────────────────────────────────

def _build_tools(graph, db_path: str | Path) -> dict:
    return {
        "get_schema_context": lambda question, top_k=10: _tools.get_schema_context(question, graph, top_k),
        "sample_values":      lambda table, column, limit=20: _tools.sample_values(table, column, db_path, limit),
        "run_sql":            lambda sql: _tools.run_sql(sql, db_path),
    }


_RETRY_AFTER_MSG = re.compile(r"try again in\s+([0-9.]+)\s*s", re.IGNORECASE)


def _retry_after_seconds(exc) -> float | None:
    """Seconds the API asked us to wait: the Retry-After header if present,
    else parsed from the message ('Please try again in 7.66s')."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            header = resp.headers.get("retry-after")
        except Exception:
            header = None
        if header:
            try:
                return float(header)
            except ValueError:
                pass
    match = _RETRY_AFTER_MSG.search(str(getattr(exc, "message", "") or exc))
    return float(match.group(1)) if match else None


def _next_wait(waited: float, retry_after: float | None,
               max_wait: float = MAX_WAIT_PER_CALL_S) -> float:
    """How long to sleep before the next retry, or raise RateLimitExhausted if
    honoring the limit would exceed the per-call budget (a daily quota, not a blip)."""
    wait = retry_after if retry_after is not None else 2.0
    if waited + wait > max_wait:
        raise RateLimitExhausted(
            f"rate limit not clearing within {max_wait:.0f}s (retry-after={wait:.1f}s); "
            "likely a daily/token quota — wait for the window to reset, raise the tier, "
            "or fall back to another model."
        )
    return wait


def _gemini_llm(api_key: str | None = None, model: str = MODEL, *, client=None, sleep=time.sleep):
    """OpenAI-compatible client pointed at Google's Gemini endpoint.
    Free tier: gemini-2.0-flash @ 1,500 req/day, 1M tokens/day."""
    client = client or OpenAI(api_key=api_key, base_url=_GEMINI_BASE_URL)

    def llm_fn(messages: list[dict], tool_schemas: list) -> LLMResponse:
        resp = None
        waited = 0.0
        while resp is None:
            try:
                resp = client.chat.completions.create(
                    model=model, messages=messages, tools=tool_schemas,
                    tool_choice="auto", temperature=0.1,
                )
            except RateLimitError as exc:
                wait = _next_wait(waited, _retry_after_seconds(exc))
                sleep(wait)
                waited += wait

        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(content=msg.content, tool_calls=calls)

    return llm_fn


def answer_question(
    question: str,
    *,
    api_key: str,
    uri: str,
    user: str,
    password: str,
    db_path: str | Path,
    model: str = MODEL,
    max_steps: int = MAX_STEPS,
    system_prompt: str | None = None,
) -> AgentResult:
    # system_prompt override wins; otherwise resolve the configured template
    # (env / bundled file / fallback) and fill in the catalog's domain list.
    domains       = [d["name"] for d in get_domains(load_schema())]
    system_prompt = system_prompt if system_prompt is not None else build_system_prompt(domains)
    graph         = _get_graph(uri, user, password)
    tool_fns      = _build_tools(graph, db_path)
    llm_fn        = _gemini_llm(api_key, model)
    return run_agent(
        question, llm_fn=llm_fn, tool_fns=tool_fns,
        system_prompt=system_prompt, max_steps=max_steps,
    )
