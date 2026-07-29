# Agent Design

The anatomy of DataPulse's one agent — the text2sql NL→SQL agent. This is the **design**
reference: what the agent is made of and why (the loop, the tool signatures, the DI seam, the
dataclasses). For the request **flow** end-to-end — the HTTP API, the caller contract, and how to
call it from code — see [query_engine.md](query_engine.md); for where the agent sits in the wider
stack see [architecture.md](architecture.md).

## One agent, two faces

There is a single agent, living as two functions in `text2sql/agent/agent.py`:

- **`run_agent(...)`** — the pure, provider-agnostic ReAct loop. Imports no
  Groq / Neo4j / SQLite. This is the crown-jewel seam; leave it as-is. It is
  unit-tested with a scripted fake model and fake tools.
- **`answer_question(...)`** — the wiring. Binds the real Groq model, the
  KG-backed tools, and the catalog-derived prompt, then calls `run_agent`.

Swapping the LLM provider means replacing one callable (`llm_fn`) — nothing in
the loop changes.

## Anatomy

```
   frontend/app.js
        │  POST /api/query  {question, top_k}
        ▼
── src/api/main.py ────────────────────────────────────────────────────
   composition root: reads env, wires dependencies
        │
        │  answer_question(question, groq_key, uri, user, pw, db_path)
        ▼
── text2sql/agent/agent.py ─────────────────────────────────────────────
   answer_question()  — WIRING
     • llm_fn        = Groq  "llama-3.3-70b-versatile"
     • tool_fns      = { get_schema_context, sample_values, run_sql }
     • system_prompt = build_system_prompt(domains)
        │
        ▼
   run_agent()  — PURE ReAct LOOP  (max_steps = 6)
        │
        │  calls the three tools until it can answer:
        ▼
     get_schema_context  → Neo4j KG  (tables, join keys, canonical metrics)
     sample_values       → SQLite    (distinct values to resolve a filter)
     run_sql             → SQLite RO  (execute the SELECT / WITH, 5s · 200 rows)

   Return: agent → main.py → browser
           { answer, sql, rows, trace[], schema_context, attempts, stopped }
```

The KG on the left is **metadata only** and is built offline by
`src/knowledge_graph/builder.py` (Domain / Table / Column / Metric nodes +
`:REFERENCES` join edges). Row data lives only in SQLite — see the two-database
split in [architecture.md](architecture.md).

## The three tools (capabilities)

The model only sees the user-facing args; the backend handles (`graph`, `db_path`)
are injected by `agent.py::_build_tools`.

| Tool | Model-facing args | Backed by | Purpose | Returns |
|---|---|---|---|---|
| `get_schema_context` | `question, top_k=10` | Neo4j KG + embeddings | Find the relevant tables, **exact join keys**, and **canonical metric definitions** — the "which tables and how do they join?" step. The prompt requires calling this first. | `{schema, tables, join_count, metrics}` |
| `sample_values` | `table, column, limit=20` | SQLite + schema.json | Read distinct real values so the agent resolves a categorical filter by looking, not guessing the literal. | `{values}` |
| `run_sql` | `sql` | SQLite (read-only) | Execute the generated `SELECT` / `WITH` query. | `{columns, rows, row_count, truncated}` |

## The loop (internals)

```
 run_agent(question, *, llm_fn, tool_fns, tool_schemas=None,
           system_prompt=SYSTEM_PROMPT, max_steps=6)
 ────────────────────────────────────────────────────────────────────────
 messages = [ system_prompt , user: question ]
      │
      ▼
 ┌─► resp = llm_fn(messages, tool_schemas)        ── asks Groq (tool_choice="auto")
 │        │
 │        ├─ NO tool_calls ───────────────────────► FINAL answer  (stopped="final")
 │        │
 │        └─ tool_calls present:
 │              for each call:
 │                 result = tool_fns[call.name](**call.arguments)
 │                            (exception → {"error": …}, never crashes the run)
 │                 append assistant + tool-result messages
 │                 record Step(kind="tool", tool, args, observation)
 │                 (run_sql → remember last_sql / last_result)
 └──────────────┘  repeat, up to max_steps = 6
      │
      ▼  (6 steps used with no final answer)
 AgentResult(answer="", stopped="max_steps", trace=[Step…], last_sql, last_result)
```

The whole "keep going vs. finish" decision is one rule: **does the model's reply
contain `tool_calls`?** If yes, run them and loop; if no, its text is the answer.
Two stopping conditions: `"final"` (model stopped calling tools) or `"max_steps"`.

## The dependency-injection seam

DI here is **structural, not typed** — there are no `Protocol` classes. The loop
depends only on:

- `llm_fn(messages, tool_schemas) -> LLMResponse` — any callable. The fake (tests)
  and the real Groq wrapper `_groq_llm` both satisfy it.
- `tool_fns: dict[str, callable]` — name → callable, invoked as `fn(**arguments)`.

The contract is carried by four small dataclasses (`agent.py`):

| Object | Kind | Fields |
|---|---|---|
| `ToolCall` | dataclass | `id, name, arguments` |
| `LLMResponse` | dataclass | `content, tool_calls: list[ToolCall]` |
| `Step` | frozen | `kind ("tool"/"final"/"stopped"), tool, args, observation` |
| `AgentResult` | dataclass | `answer, trace: list[Step], stopped, last_sql, last_result` |

Because reasoning is a **trace of explicit `Step`s**, the UI can show which tables
the model discovered, what SQL it tried, and where it corrected itself — not one
opaque generation.

## Inside `get_schema_context` (how it plans)

```
 embed_query(question) ─► 384-d vector      (sentence-transformers all-MiniLM-L6-v2)
      │
      ▼   SchemaGraph over Neo4j vector indexes + :REFERENCES edges
 1. route_domains    rank :Domain by vector sim         (soft routing, no hard cut)
 2. search_columns   vector search :Column  (+ domain-scoped recall boost)
    search_tables    vector search :Table
 3. seed tables      pick seeds from the hits
 4. join_paths       shortestPath over :REFERENCES (≤ 3 hops) → exact join keys
    self_joins       self-FKs (e.g. employees.manager_id → employees.employee_id)
 5. fetch_tables     columns / types / PK / allowed_values
    fetch_metrics    canonical metric expressions (semantic layer)
      │
      ▼
 { schema: <markdown>, tables, join_count, metrics }
```

## Built to survive a flaky model

| Concern | Mechanism | Where |
|---|---|---|
| SQL safety | `SELECT`/`WITH` allowlist; blocks writes/DDL; single statement only | `tools.py::read_only_violation` |
| DB safety | read-only connection (`?mode=ro`), 5s timeout, 200-row cap | `tools.py::run_sql` |
| Injection | table/column validated against `schema.json` before quoting | `tools.py::sample_values` |
| Tool crash isolation | any tool exception → `{"error": …}` fed back to the model | `agent.py::run_agent` |
| Rate limits | honor `Retry-After`; raise `RateLimitExhausted` past a 60s/call budget | `agent.py::_next_wait` |
| Malformed tool call | regex-recover Llama's `<function=…>` token that Groq rejects | `agent.py::_recover_tool_calls` |

A rejection or a tool error is a structured message the agent reads and reforms — a bad query, a
flaky call, or a transient limit never crashes the run. The SQL allowlist (`read_only_violation`)
permits a single `SELECT` / `WITH` (with a trailing semicolon or comments) and rejects writes/DDL
(`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, ...), multiple statements, and
empty input.

For how a *caller* should surface `RateLimitExhausted` (and the HTTP error envelope the API wraps
it in), see [query_engine.md § Rate-limit handling](query_engine.md#rate-limit-handling-groq).

## What it stands on

| Layer | Component | Role for the agent |
|---|---|---|
| Model | Groq `llama-3.3-70b-versatile` (`temp=0.1`) | Reasons, and picks which tool to call |
| Knowledge graph | Neo4j (`knowledge_graph/`) | Metadata-only schema graph: nodes + `:REFERENCES` join edges + 3 vector indexes (384-d cosine) |
| Embeddings | `all-MiniLM-L6-v2`, local | 384-d normalized vectors for question ↔ node similarity |
| Execution DB | SQLite `db/sales.db` | The actual data; the agent only ever reads it |
| Catalog | `metadata/schema.json` + `utils.py` | Single source of truth — feeds the prompt, the KG build, and identifier validation |

Required env: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `GROQ_API_KEY`.

## See also

- [query_engine.md](query_engine.md) — the request flow, HTTP surface, and calling from code
- [architecture.md](architecture.md) — the four layers and the two-database split
- [data_model.md](data_model.md) — the catalog the agent plans against
