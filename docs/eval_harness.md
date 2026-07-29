# Eval harness — measuring answer accuracy

DataPulse is a reasoning knowledge agent (`run_agent` is a real tool-calling ReAct
loop). This harness makes its accuracy **measurable** so "accurate" is falsifiable,
and it backs the trustworthiness fixes (honest `success`, answer grounding).

Everything here is deterministic and offline-runnable; the live baseline is the one
step that needs credentials (see [Handoff](#handoff-needs-live-creds)).

## What's where

| Piece | Path | Role |
|---|---|---|
| The ruler | `text2sql/eval/scoring.py` | `result_match` — tolerant value-*multiset containment* (rounds floats, strips `$ , %`, ignores column names/aliases + row order). The primary accuracy metric. |
| Grounding signal | `text2sql/agent/grounding.py` | `answer_grounded` / `check_grounding` — do the answer's figures appear in the rows? **Advisory only**, never gates `success` or the pass-rate. |
| Gold set | `text2sql/eval/gold_questions.jsonl` | ~15 NL→SQL questions across all 5 domains, each with a committed expected value validated against the seed-42 `sales.db`. Includes the known traps (revenue column, fan-out, self-join, cross-domain-unjoinable) and derived-value questions. |
| Runner | `text2sql/eval/run_eval.py` | Drives `run_agent` over the gold set, scores, writes `eval_report.json`. |

## Running it

```bash
# Offline (deterministic, no network, CI-safe): a scripted fake model runs the
# canonical SQL via the real run_sql tool. Validates the scoring + plumbing.
uv run python -m text2sql.eval.run_eval --offline

# Live baseline (needs .env: NEO4J_* + GROQ_API_KEY). Rate-limit-aware and
# resumable — re-run to continue after a free-tier quota stop. --limit caps it.
uv run python -m text2sql.eval.run_eval --limit 10
```

`eval_report.json` (gitignored) reports overall + per-domain pass-rate and the
grounding **false-negative rate** on derived questions (grounding is diagnostic; it
false-negatives on derived figures like "4.06 orders per customer" that appear in no
single cell — which is exactly why it never gates).

## Key scoring rules (why the ruler is trustworthy)

- **Right answer, wrong shape ⇒ match.** `AS revenue` vs `AS total_revenue`,
  `1200000.0` vs `1200000.00`, INTEGER-vs-REAL, an extra grouping column, and
  scalar-vs-single-row all read as matches. A ruler that failed these would
  mis-order every downstream fix. Adversarial pairs live in `test_eval_scoring.py`.
- **Wrong answer ⇒ fail.** The revenue trap (`order_items.line_total` 7,782,964.89
  vs `invoices.amount` 2,030,281.53) is rejected.
- **Cross-domain "unjoinable"** is scored on graceful degradation (`score_unjoinable`),
  not numeric containment: it passes if the agent produced no fabricated join.
  Its `success=False` is the **correct** outcome (no SQL backs a non-answer).

## Drift guard

`tests/text2sql/test_eval_gold.py` re-runs each gold SQL against the tracked
`sales.db` and asserts the committed expected value still holds — the same
philosophy as the seed-42 determinism gate. If schema/data drifts, it fails loudly
here instead of silently corrupting the baseline. Regenerate committed values from
the DB and re-commit `gold_questions.jsonl` after any intended data change.

## Handoff (needs live creds)

These were **not** run in the implementing session (no reachable Neo4j/Groq) and are
the operator's step:

1. **Rebuild the KG** after the `schema.json` edits (added join `cardinality` +
   9 domain metrics — metadata only, verified not to change `sales.db`/CSVs by
   `pytest -k seed42`):
   ```bash
   uv run python -m src.knowledge_graph.builder      # or /run-pipeline
   ```
   Then confirm `GET /api/health` → `kg_fresh: true`. Until rebuilt the retriever
   still works: `cardinality` defaults to null and the fan-out warning is simply
   omitted (backward-compatible).
2. **Live baseline → delta.** Two traps to avoid, or the delta will be a
   misleading zero:
   - **The "before" baseline is not in this tree** — the fixes are already applied
     (and, once committed, in history). To capture a true pre-fix baseline you must
     stash/checkout the pre-fix code for that run:
     ```bash
     git stash                                                   # or: git checkout <pre-fix-sha>
     uv run python -m text2sql.eval.run_eval --limit 10 \
       --checkpoint eval_before.jsonl --output eval_before.json
     git stash pop                                               # restore the fixes
     uv run python -m text2sql.eval.run_eval --limit 10 \
       --checkpoint eval_after.jsonl  --output eval_after.json
     ```
   - **Use distinct `--checkpoint` AND `--output` per run** (as above). Both default
     to fixed paths and the runner *resumes* any existing checkpoint — reusing one
     path makes the second run skip every done id and re-emit the first run's
     numbers. (`--fresh` clears the default checkpoint if you prefer that over
     distinct paths.) Then diff `eval_before.json` vs `eval_after.json`.
   - A/B the prompt-hardening change in isolation first — prompt changes on a 70b
     free model can regress (verbosity, over-refusal) as easily as help; batching it
     with Phase 3 makes the delta unattributable.
3. **Eval-gated options (only if the report shows the need):** bump `MAX_STEPS` 6→8
   (`agent.py`); add 2–3 few-shot Q→SQL exemplars to the system prompt (Phase 4).

## Not done (deliberate)

- Prune the never-traversed `(:Column)-[:FOREIGN_KEY]->(:Column)` edge in the
  builder — low priority, left as-is (the `:REFERENCES` table projection is what the
  retriever walks).
- Multi-agent Planner→SQL→Synthesizer and fact-graph reasoning-*over*-facts — out of
  scope (free-tier LLM cost); see `docs/multi_agent_plan.md` and the plan's
  "reasoning over a fact graph" notes.
