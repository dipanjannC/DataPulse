# Multi-Agent Redesign — Action Plan

> **Status: proposal, not implemented.** Today DataPulse runs *one* unified ReAct agent
> ([agents_design.md](agents_design.md)), and that is the right default. Pick this up only on a real
> trigger (below). This is the "if we go multi-agent" playbook — the prerequisites, the target
> shape, and the exact blocks to refactor.

## When to do this (triggers)

Reach for this only when one of these is actually true:

- **A measured answer-quality gap** that prompt-tuning (`build_system_prompt`) did not close — e.g.
  answers that are vague, badly formatted, or cite numbers not in the returned rows.
- **A deliberate multi-agent showcase** — the "planner → SQL → synthesizer" story is worth telling
  for its own sake (demo, stakeholder narrative).

If neither holds, stop — the single agent wins on cost, latency, and simplicity.

## Prerequisites (what you need first)

| Need | Why |
|---|---|
| **Higher Groq limits (paid / dev tier)** | A question already costs several calls today (it is a loop — one call per step); three agents means three loops, so round-trips and daily-quota burn multiply. This is the real blocker — not RPM. |
| **An A/B eval harness** | To prove the split actually beats the single agent on answer quality. A handful of golden questions + a diff of the answers is enough to start. |
| **Agreed state contracts** | What the Planner hands the SQL agent (the "plan"), and what the SQL agent hands the Synthesizer (sql + rows). Fixed in the table below. |

## The shape

Three specialized agents run as a pipeline. **The key move: do not rewrite the loop — reuse it.**
Each agent is the *same* `run_agent` primitive, specialized by `(prompt, tool subset, model)`. An
**orchestrator** sequences them and merges their traces into one.

```
 BEFORE  — one unified agent (today)

   question ─► run_agent   (loops until it can answer; one model, one trace)
                  │  calls, as needed:
                  ├─ get_schema_context   (KG)
                  ├─ sample_values        (SQLite)
                  └─ run_sql              (SQLite)
                  ▼
              answer + sql + rows + trace


 AFTER  — three agents, orchestrated (proposed)

   question
      │
      ▼
   [1] Planner ──────► get_schema_context        plan = {tables, join keys, metrics}
      │
      ▼
   [2] SQL ──────────► sample_values, run_sql     sql + rows
      │
      ▼
   [3] Synthesizer     (no tools, one call)       grounded NL answer
      │
      ▼
   answer + sql + rows + ONE merged, phase-tagged trace
```

The agents and their contracts:

| Agent | Input | Tools | Output | Model |
|---|---|---|---|---|
| **Planner** | `question` | `{get_schema_context}` | plan: relevant tables, join keys, metrics | 70b |
| **SQL** | `question` + plan | `{sample_values, run_sql}` | winning SQL + result rows | 70b |
| **Synthesizer** | `question` + sql + rows | `{}` (none) | final NL answer, grounded in the rows | 8b-instant (cheaper is fine) |

The orchestrator is the multi-agent analog of today's `answer_question` — pure composition over the
existing loop:

```
 run_pipeline(question):
     plan       = run_agent(question,            prompt=PLANNER, tools={get_schema_context})
     sql, rows  = run_agent(question + plan,     prompt=SQL,     tools={sample_values, run_sql})
     answer     = run_agent(question + sql+rows, prompt=SYNTH,   tools={}, tool_schemas=[])
     trace      = plan.trace + sql.trace + answer.trace          # each Step tagged with .phase
     return AgentResult(answer, trace, stopped, last_sql=sql, last_result=rows)
```

Because the orchestrator returns the *same* `AgentResult` shape, the `/api/query` payload and the
frontend barely change — the trace just gets richer (phase-tagged).

`prompt=` / `tools=` above are shorthand for `system_prompt=` / `tool_fns=`. The synth agent passes
`tool_schemas=[]` explicitly: the default `None` re-offers the full `TOOL_SCHEMAS`, so with empty
`tool_fns` the model would try to call tools that have no implementation. Empty tools ⇒ it answers
on turn one (one LLM call).

### The planner → SQL handoff (decide this first)

`run_agent` surfaces only `last_sql` / `last_result` (set on a `run_sql` call) — it has **no field
for `get_schema_context`'s output**. So the SQL agent's result threads forward cleanly, but the
planner's schema context does not. Pick one:

- **Plan = the planner's NL directive** (intent, target tables, which metric). `run_agent` is
  genuinely unchanged — but the SQL agent gets prose, not exact join keys, so it still calls
  `get_schema_context` itself. The planner adds intent / decomposition, not schema-passing.
- **Plan = the structured schema context** (exact join keys, columns, `allowed_values`). The SQL
  agent skips retrieval — but you must surface tool results from `run_agent` (add a `tool_results`
  field to `AgentResult`), a real, if small, change to the loop beyond `Step.phase`.

Start with the NL-directive option (zero loop change); add structured passing only if evals show the
SQL agent needs the planner's exact schema.

## What to refactor (developer checklist)

Blast radius is small. With the NL-directive handoff (above), **`run_agent`'s control flow does not
change at all** — everything below is new code beside the single-agent path. The structured-handoff
option adds exactly one field (`tool_results`) to `run_agent` / `AgentResult`; that is the only
extra touch to the loop.

| Block | Change | Kind |
|---|---|---|
| `agent.py` — `Step` | add `phase: str = ""` (frozen + defaulted, so existing traces stay valid) | edit (1 line) |
| `agent.py` — prompts | add `PLANNER_PROMPT`, `SQL_PROMPT`, `SYNTH_PROMPT` (builders, like `build_system_prompt`) | new |
| `agent.py` — schemas | split module-level `TOOL_SCHEMAS` into per-agent subsets (`PLANNER_SCHEMAS`, `SQL_SCHEMAS`, `[]`) | new |
| `agent.py` — orchestrator | `run_pipeline(...)`: sequence the three `run_agent` calls, tag each returned Step's phase via `dataclasses.replace`, thread state, concat traces | new |
| `agent.py` — wiring | `answer_question_multi(...)` beside `answer_question` (same signature; optional per-phase model overrides) | new |
| `tools.py` | none — tools are unchanged; agents just receive subsets of `_build_tools(...)` | — |
| `api/main.py` | `AGENT_MODE=single\|multi` env switch selects the wiring; `_trace_payload` emits the new `phase` | edit |
| `frontend/app.js` + `style.css` | group trace Steps into phase lanes; fall back to one lane when `phase` is empty | edit |
| `tests/text2sql/` | new `test_orchestrator.py` — a scripted fake model per phase; keep every single-agent test green | new |

Because `run_agent` stays intact and `Step.phase` defaults to empty, the single-agent path is fully
backward compatible — the multi path is pure addition.

```
 One trace, three lanes (frontend groups Steps by .phase):

   PLAN   │ get_schema_context -> 4 tables · 3 join keys · 2 metrics
   SQL    │ run_sql (try 1) -> error: no such column ; run_sql (try 2) -> 12 rows
   ANSWER │ "Revenue by region for 2024: North 1.2M, ..."
```

## Rollout

1. Land the backend behind `AGENT_MODE` (default `single`); the `multi` path is opt-in.
2. Run the A/B eval — only flip the default if answers measurably improve.
3. Add the phased-trace rendering. Cheaper synth model + prompt tuning come last.

## Trade-offs (go in with eyes open)

- **Three loops instead of one** — latency, cost, and daily-quota burn multiply (a question is
  already several calls; now it is three agents' worth). The paid tier is non-negotiable.
- **More surface to maintain** — three prompts instead of one; they drift.
- **Inter-agent failure** — a bad plan starves the SQL agent. Decide the fallback up front: retry
  the planner, or degrade to the single-agent path.
- **You may not need it** — if the goal is just better answers, tuning `build_system_prompt` on the
  current agent is one call, one trace, and far less code. See [agents_design.md](agents_design.md).

## See also

- [agents_design.md](agents_design.md) — the current single-agent design this would replace
- [query_engine.md](query_engine.md) — the request flow and the `/api/query` contract to preserve
