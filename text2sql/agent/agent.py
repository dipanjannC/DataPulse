"""A small tool-calling agent that plans NL -> SQL over the knowledge graph.

The loop is deliberately dependency-injected: `run_agent` takes an `llm_fn`
(messages, tool_schemas) -> LLMResponse and a `tool_fns` registry, so the
iteration / trace / guard logic is unit-tested with a scripted fake model and
fake tools — no live Groq/Neo4j/SQLite. `answer_question` wires the real Groq
client and the KG-backed tools.

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

from groq import BadRequestError, Groq, RateLimitError

from text2sql.agent import tools as _tools
from src.knowledge_graph.retriever import _get_graph
from src.metadata.utils import get_domains, load_schema

MODEL     = "llama-3.3-70b-versatile"
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


_SYSTEM_PROMPT_TEMPLATE = """\
You are DataPulse, an analyst that answers business questions by querying a SQLite
database spanning {domains}. You work by calling
tools, observing the results, and refining — never guess table or column names.

Tools:
- get_schema_context(question): returns the relevant tables, exact join keys, and
  canonical METRIC DEFINITIONS. Call this FIRST, before writing any SQL.
- sample_values(table, column): distinct values of a column — use it to resolve a
  categorical filter (e.g. a status or tier) instead of guessing the literal.
- run_sql(sql): runs a read-only SELECT/WITH query and returns rows.

Rules:
- Always call get_schema_context before writing SQL, and use the exact join keys it
  gives you.
- For a business measure (revenue, margin, attainment, etc.), use the exact expression
  from the "Metric definitions" section verbatim — do NOT substitute a similar-looking
  column (e.g. never use invoices.amount for revenue).
- Only read-only SELECT/WITH queries. If run_sql returns an error or unexpected/empty
  rows, read it, fix the query, and try again.
- When you have the answer, reply in plain language and state the key number(s).
"""


def _domains_phrase(domains: list[str]) -> str:
    names = [d for d in domains if d]
    if not names:
        return "multiple business domains"
    if len(names) == 1:
        return f"{names[0]} data"
    return ", ".join(names[:-1]) + f", and {names[-1]} data"


def build_system_prompt(domains: list[str]) -> str:
    """Fill the system-prompt template with the domain list. Derived from the
    catalog at wiring time so a new domain needs no prompt edit."""
    return _SYSTEM_PROMPT_TEMPLATE.format(domains=_domains_phrase(domains))


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


# ── real wiring (Groq + KG-backed tools) ────────────────────────────────────────

def _build_tools(graph, db_path: str | Path) -> dict:
    return {
        "get_schema_context": lambda question, top_k=10: _tools.get_schema_context(question, graph, top_k),
        "sample_values":      lambda table, column, limit=20: _tools.sample_values(table, column, db_path, limit),
        "run_sql":            lambda sql: _tools.run_sql(sql, db_path),
    }


# Llama on Groq intermittently emits its native tool-call token instead of a
# structured call, which Groq rejects with `tool_use_failed`. The intended call
# is still in `failed_generation`, so we recover it rather than crash the run.
_FUNC_TOKEN = re.compile(r"<function=([A-Za-z_]\w*)\s*(\{.*?\})\s*</function>", re.DOTALL)


def _recover_tool_calls(exc: BadRequestError) -> list[ToolCall]:
    body = getattr(exc, "body", None)
    failed = ""
    if isinstance(body, dict):
        failed = (body.get("error") or {}).get("failed_generation") or ""
    calls: list[ToolCall] = []
    for i, (name, raw_args) in enumerate(_FUNC_TOKEN.findall(failed)):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            continue
        calls.append(ToolCall(id=f"recovered-{i}", name=name, arguments=args))
    return calls


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


def _groq_llm(api_key: str | None = None, model: str = MODEL, *, client=None, sleep=time.sleep):
    client = client or Groq(api_key=api_key)

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
                wait = _next_wait(waited, _retry_after_seconds(exc))  # raises on daily quota
                sleep(wait)
                waited += wait
            except BadRequestError as exc:
                recovered = _recover_tool_calls(exc)
                if recovered:
                    return LLMResponse(content=None, tool_calls=recovered)
                raise

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
    groq_key: str,
    uri: str,
    user: str,
    password: str,
    db_path: str | Path,
    model: str = MODEL,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    domains       = [d["name"] for d in get_domains(load_schema())]
    system_prompt = build_system_prompt(domains)
    graph         = _get_graph(uri, user, password)
    tool_fns      = _build_tools(graph, db_path)
    llm_fn        = _groq_llm(groq_key, model)
    return run_agent(
        question, llm_fn=llm_fn, tool_fns=tool_fns,
        system_prompt=system_prompt, max_steps=max_steps,
    )
