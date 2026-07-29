# Query Engine (CONSUME)

How a natural-language question becomes SQL and rows in the active stack — the request
**flow** and the operational surface. For the agent's internal **design** (loop mechanics,
tool signatures, the DI seam, dataclasses) see [agents_design.md](agents_design.md). For the
legacy `src/` google-adk/Cypher engine see [legacy_src.md](legacy_src.md).

## The agent loop

The core is `run_agent` in `text2sql/agent/agent.py` — a small, dependency-injected loop (its
mechanics, the DI seam, and the result/trace dataclasses live in
[agents_design.md](agents_design.md)). The model works by calling tools in a loop until it can
answer:

```
NL question
   │
   ▼
llm_fn (Groq: llama-3.3-70b-versatile)
   │  decides a tool call
   ├─▶ get_schema_context(question) ──▶ Neo4j KG  ─▶ relevant tables, join keys, metric defs
   ├─▶ sample_values(table, column) ──▶ SQLite    ─▶ distinct values (resolve a filter literal)
   └─▶ run_sql(sql)                 ──▶ SQLite    ─▶ rows  (read-only, guarded)
   │  reads observations, may loop (up to MAX_STEPS = 6)
   ▼
final natural-language answer + the SQL + the rows + an inspectable trace
```

That reasoning trace — the tables discovered, the SQL attempted, the corrections — comes back in
the `trace` field of every response, so an answer is never one opaque generation.

## The three tools

The loop calls three tools — `get_schema_context` (Neo4j KG), `sample_values` (SQLite), and
`run_sql` (SQLite, read-only) — shown as steps in the diagram above. Their signatures, backends,
return shapes, and guardrails are documented once in
[agents_design.md § The three tools](agents_design.md#the-three-tools-capabilities). Three facts
that matter to the *flow*:

- The prompt **requires calling `get_schema_context` first** — the agent discovers the relevant
  tables and join keys before it writes any SQL.
- `run_sql` runs **only a single read-only `SELECT`/`WITH`**; a rejected query comes back as a
  structured error the agent reforms, never a crash.
- The prompt's domain list is **derived from the catalog** at wiring time
  (`build_system_prompt(get_domains(load_schema()))`), so adding a domain needs no prompt edit.

## Two entry points

`run_agent` (the pure, provider-agnostic loop) and `answer_question` (the wiring that binds
Groq + Neo4j + SQLite and calls it) — the full breakdown is in
[agents_design.md § One agent, two faces](agents_design.md#one-agent-two-faces). The example
below calls `answer_question`, which returns an
`AgentResult(answer, trace, stopped, last_sql, last_result)`.

## Rate-limit handling (Groq)

Groq's free tier throttles quickly. The `llm_fn` honors `Retry-After` for **transient** per-minute
limits, but raises `RateLimitExhausted` if a single wait would exceed a per-call budget
(`MAX_WAIT_PER_CALL_S = 60`) — i.e. a daily/token quota, where blocking is pointless. Callers (the
API, a batch eval) should surface it and resume later rather than hammer. (The mechanism, alongside
the SQL guard and Llama malformed-tool-call recovery, is in
[agents_design.md § Built to survive a flaky model](agents_design.md#built-to-survive-a-flaky-model).)

## HTTP surface (`api/main.py`)

The FastAPI app is both the API and the UI host.

| Route | Purpose |
|---|---|
| `POST /api/query` | Body `{ "question": str, "top_k": 10 }` → `{ success, answer, sql, columns, rows, schema_context, trace, attempts, stopped, error }`. Runs `answer_question`; a `RateLimitExhausted` returns `success:false, stopped:"rate_limited"` (not a 500). |
| `GET /api/health` | Liveness + whether Neo4j is reachable. |
| `GET /api/domains` | Domain list for the UI. |
| `GET /` , `/static/*` | Serves the static `frontend/` (so the UI and API share one origin). |

Required env: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `GROQ_API_KEY`.

## Calling from code

```python
from text2sql.agent.agent import answer_question
from src.db.loader import DB_PATH

result = answer_question(
    "What is total revenue by region for 2024?",
    groq_key=..., uri=..., user=..., password=..., db_path=DB_PATH,
)
print(result.answer)
print(result.last_sql)
for step in result.trace:      # inspect the tool-call reasoning
    print(step.kind, step.tool, step.observation)
```

Run the API with `uv run uvicorn src.api.main:app --reload --port 8000`, then open
`http://localhost:8000/`.
