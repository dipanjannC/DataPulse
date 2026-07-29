"""Eval runner — drive `run_agent` over the gold set and report accuracy.

Two modes:

- ``--offline`` (deterministic, no network, CI-safe): a scripted fake ``llm_fn``
  per gold question drives the *real* ``run_agent`` loop and the *real*
  ``run_sql`` tool against the tracked ``sales.db``, exactly like
  ``tests/text2sql/test_agent.py``. This exercises the scoring + plumbing without
  Groq/Neo4j and must pass every gold question (the SQL *is* the canonical SQL).

- live (default; needs ``.env`` creds): the real Groq + KG-backed agent. Wrapped
  to catch ``RateLimitExhausted`` (built for exactly this) — it checkpoints
  completed questions to a resumable file and stops, so the free-tier quota is
  never hammered. ``--limit N`` caps the run; re-running resumes where it left off.

Establishes the accuracy baseline and, after the fixes, the delta. Writes a
gitignored ``eval_report.json`` with overall + per-domain pass-rate and the
grounding false-negative rate (grounding is diagnostic, never part of pass-rate).

    uv run python -m text2sql.eval.run_eval --offline
    uv run python -m text2sql.eval.run_eval --limit 10        # live baseline
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from text2sql.agent.agent import (
    LLMResponse,
    RateLimitExhausted,
    ToolCall,
    answer_question,
    run_agent,
)
from text2sql.agent.grounding import answer_grounded
from text2sql.agent.tools import run_sql
from text2sql.eval.scoring import result_match, score_unjoinable

logger = logging.getLogger(__name__)

_REPO_ROOT         = Path(__file__).resolve().parents[2]
GOLD_PATH          = Path(__file__).resolve().parent / "gold_questions.jsonl"
DEFAULT_REPORT     = _REPO_ROOT / "eval_report.json"
DEFAULT_CHECKPOINT = _REPO_ROOT / "eval_checkpoint.jsonl"
DEFAULT_DB         = _REPO_ROOT / "src" / "db" / "sales.db"


# ── gold set ────────────────────────────────────────────────────────────────

def load_gold(path: Path | str = GOLD_PATH) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


# ── scoring one agent run (pure; shared by offline + live) ──────────────────

def score_result(entry: dict, result) -> dict:
    """Score one AgentResult against a gold entry. ``result_match`` is the
    accuracy verdict; ``answer_grounded`` is recorded diagnostically and never
    flips ``passed``."""
    mode   = entry["match_mode"]
    answer = result.answer
    last   = result.last_result

    if mode == "unjoinable":
        passed  = score_unjoinable(answer, last)
        grounded = None
    else:
        passed   = result_match(entry["expected"], last, mode=mode)
        grounded = answer_grounded(answer, last)

    grounding_kind = entry.get("grounding", "direct")
    false_negative = bool(passed and grounded is False and grounding_kind == "derived")

    return {
        "id":             entry["id"],
        "domain":         entry["domain"],
        "match_mode":     mode,
        "grounding_kind": grounding_kind,
        "passed":         bool(passed),
        "grounded":       grounded,
        "grounding_false_negative": false_negative,
        "stopped":        result.stopped,
        "attempts":       sum(1 for s in result.trace if s.tool == "run_sql"),
        "answer":         (answer or "")[:300],
        "error":          None,
    }


# ── offline mode (scripted fake llm_fn; deterministic) ──────────────────────

def _offline_llm(entry: dict):
    """A scripted model: look up schema, run the canonical SQL, then state the
    expected value(s) so the grounding signal has something to verify. The
    unjoinable case runs no SQL and states non-joinability."""
    if entry["match_mode"] == "unjoinable":
        steps = [
            LLMResponse(None, [ToolCall("c1", "get_schema_context", {"question": entry["question"]})]),
            LLMResponse("These tables are in separate domains with no defined join key and cannot be joined.", []),
        ]
    else:
        restated = ", ".join(str(v) for v in entry["expected"])
        steps = [
            LLMResponse(None, [ToolCall("c1", "get_schema_context", {"question": entry["question"]})]),
            LLMResponse(None, [ToolCall("c2", "run_sql", {"sql": entry["sql"]})]),
            LLMResponse(f"Based on the query results, the answer is: {restated}.", []),
        ]
    it = iter(steps)

    def llm_fn(messages, tool_schemas):
        return next(it)

    return llm_fn


def _offline_tools(db_path: Path | str) -> dict:
    # get_schema_context is stubbed (no Neo4j); run_sql is REAL against sales.db.
    return {
        "get_schema_context": lambda question, top_k=10: {
            "tables": [], "metrics": [], "schema": "(offline: KG retrieval skipped)"},
        "run_sql":            lambda sql: run_sql(sql, db_path),
        "sample_values":      lambda table, column, limit=20: {"values": []},
    }


def run_offline(gold: list[dict], db_path: Path | str = DEFAULT_DB) -> list[dict]:
    tool_fns = _offline_tools(db_path)
    return [
        score_result(entry, run_agent(entry["question"], llm_fn=_offline_llm(entry), tool_fns=tool_fns))
        for entry in gold
    ]


# ── live mode (real Groq + KG; rate-limit-aware, resumable) ─────────────────

def _load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    done: dict[str, dict] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rec = json.loads(ln)
            done[rec["id"]] = rec
    return done


def _append_checkpoint(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def run_live(gold: list[dict], *, db_path: Path, checkpoint_path: Path,
             creds: dict) -> list[dict]:
    done = _load_checkpoint(checkpoint_path)
    if done:
        logger.info("resuming: %d question(s) already scored in %s", len(done), checkpoint_path.name)
    records: list[dict] = list(done.values())

    for entry in gold:
        if entry["id"] in done:
            continue
        try:
            result = answer_question(
                entry["question"],
                groq_key=creds["groq_key"], uri=creds["uri"],
                user=creds["user"], password=creds["password"], db_path=db_path,
            )
        except RateLimitExhausted as exc:
            logger.warning(
                "rate limit exhausted at %s: %s — %d done, checkpointed; re-run to resume",
                entry["id"], exc, len(records),
            )
            break
        except Exception as exc:  # one bad question must not sink the batch
            logger.exception("agent error on %s", entry["id"])
            record = {
                "id": entry["id"], "domain": entry["domain"], "match_mode": entry["match_mode"],
                "grounding_kind": entry.get("grounding", "direct"), "passed": False,
                "grounded": None, "grounding_false_negative": False, "stopped": "error",
                "attempts": 0, "answer": "", "error": str(exc)[:200],
            }
        else:
            record = score_result(entry, result)
            logger.info("%-40s %s", entry["id"], "PASS" if record["passed"] else "FAIL")

        records.append(record)
        _append_checkpoint(checkpoint_path, record)

    return records


# ── aggregation + report ────────────────────────────────────────────────────

def aggregate(records: list[dict]) -> dict:
    scored = [r for r in records if r.get("error") is None]
    total  = len(scored)
    passed = sum(1 for r in scored if r["passed"])

    by_domain: dict[str, dict] = {}
    for r in scored:
        d = by_domain.setdefault(r["domain"], {"total": 0, "passed": 0})
        d["total"] += 1
        d["passed"] += 1 if r["passed"] else 0

    derived = [r for r in scored if r["grounding_kind"] == "derived" and r["grounded"] is not None]
    fn      = sum(1 for r in derived if r["grounding_false_negative"])

    return {
        "overall": {
            "total": total, "passed": passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        },
        "by_domain": {
            d: {**v, "pass_rate": round(v["passed"] / v["total"], 4) if v["total"] else 0.0}
            for d, v in sorted(by_domain.items())
        },
        "grounding_diagnostic": {
            "derived_questions": len(derived),
            "false_negatives": fn,
            "false_negative_rate": round(fn / len(derived), 4) if derived else 0.0,
            "note": "answer_grounded is diagnostic only and never affects pass_rate; it false-negatives on derived values.",
        },
        "errors": [r["id"] for r in records if r.get("error")],
        "records": records,
    }


def _log_summary(report: dict) -> None:
    ov = report["overall"]
    logger.info("overall: %d/%d passed (%.1f%%)", ov["passed"], ov["total"], 100 * ov["pass_rate"])
    for domain, v in report["by_domain"].items():
        logger.info("  %-14s %d/%d (%.0f%%)", domain, v["passed"], v["total"], 100 * v["pass_rate"])
    g = report["grounding_diagnostic"]
    logger.info("grounding FN (diagnostic): %d/%d derived (%.0f%%)",
                g["false_negatives"], g["derived_questions"], 100 * g["false_negative_rate"])
    if report["errors"]:
        logger.warning("errored questions: %s", ", ".join(report["errors"]))


# ── CLI ─────────────────────────────────────────────────────────────────────

def _require_creds() -> dict | None:
    creds = {
        "uri":      os.getenv("NEO4J_URI"),
        "user":     os.getenv("NEO4J_USERNAME"),
        "password": os.getenv("NEO4J_PASSWORD"),
        "groq_key": os.getenv("GROQ_API_KEY"),
    }
    if not all(creds.values()):
        return None
    return creds


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the DataPulse SQL-agent accuracy eval.")
    p.add_argument("--offline", action="store_true",
                   help="Deterministic scripted run (no Groq/Neo4j); default is live.")
    p.add_argument("--limit", type=int, default=None, help="Only run the first N gold questions.")
    p.add_argument("--gold", type=Path, default=GOLD_PATH)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    p.add_argument("--fresh", action="store_true", help="Ignore any existing live checkpoint and start over.")
    return p.parse_args(argv)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()
    args = _parse_args()

    gold = load_gold(args.gold)
    if args.limit is not None:
        gold = gold[: args.limit]

    if args.offline:
        logger.info("offline eval over %d gold question(s)", len(gold))
        records = run_offline(gold, args.db)
    else:
        creds = _require_creds()
        if creds is None:
            logger.error("live eval needs NEO4J_URI/USERNAME/PASSWORD + GROQ_API_KEY in the environment "
                         "(.env). Use --offline for a no-network run.")
            return 1
        if args.fresh and args.checkpoint.exists():
            args.checkpoint.unlink()
        logger.info("live eval over %d gold question(s)", len(gold))
        records = run_live(gold, db_path=args.db, checkpoint_path=args.checkpoint, creds=creds)

    report = aggregate(records)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("wrote %s", args.output)
    _log_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
