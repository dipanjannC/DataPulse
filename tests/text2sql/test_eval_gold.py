"""Gold-set integrity + offline-eval plumbing.

The drift guard mirrors the seed42 determinism gate: each gold question's
canonical SQL, run against the tracked ``sales.db``, must still yield its
committed expected value — so a schema/data change that silently moves a number
fails loudly here instead of corrupting the accuracy baseline. The offline-eval
test exercises the *real* ``run_agent`` loop + ``run_sql`` against the fake model,
proving the scoring + plumbing end to end with no network.
"""
from __future__ import annotations

from types import SimpleNamespace

from text2sql.agent.tools import run_sql
from text2sql.eval.run_eval import (
    DEFAULT_DB,
    aggregate,
    load_gold,
    run_offline,
    score_result,
)
from text2sql.eval.scoring import result_match


def test_gold_set_spans_all_domains_and_traps():
    gold = load_gold()
    domains = {g["domain"] for g in gold}
    assert {"Sales", "IT", "HR", "Marketing", "Security", "cross-domain"} <= domains
    traps = {t for g in gold for t in g.get("traps", [])}
    assert {"revenue-column", "fan-out", "self-join", "cross-domain", "derived-value"} <= traps


def test_every_gold_sql_yields_its_committed_expected():
    """Drift guard: canonical SQL vs committed expected, against the tracked DB."""
    for entry in load_gold():
        if entry["match_mode"] == "unjoinable":
            assert not entry["sql"], f"{entry['id']}: unjoinable questions carry no SQL"
            continue
        result = run_sql(entry["sql"], DEFAULT_DB)
        assert "error" not in result, f"{entry['id']}: SQL failed -> {result.get('error')}"
        assert result_match(entry["expected"], result, mode=entry["match_mode"]), (
            f"{entry['id']} drifted: expected {entry['expected']} not found in {result['rows']}"
        )


def test_offline_eval_passes_every_gold_question():
    gold = load_gold()
    records = run_offline(gold, DEFAULT_DB)
    report = aggregate(records)

    failed = [r["id"] for r in records if not r["passed"]]
    assert report["overall"]["total"] == len(gold)
    assert report["overall"]["passed"] == len(gold), f"offline failures: {failed}"
    assert report["overall"]["pass_rate"] == 1.0
    # every domain (incl. the cross-domain degradation case) is represented
    assert set(report["by_domain"]) >= {
        "Sales", "IT", "HR", "Marketing", "Security", "cross-domain"}


def test_offline_answers_restate_numbers_so_no_grounding_false_negative():
    # offline synthetic answers restate the exact expected figures, so grounding
    # never false-negatives here; the real FN rate is a live-mode measurement.
    records = run_offline(load_gold(), DEFAULT_DB)
    assert all(not r["grounding_false_negative"] for r in records)


def test_score_result_records_grounding_fn_without_flipping_pass():
    entry = {"id": "x", "domain": "Sales", "match_mode": "contains",
             "expected": [10], "grounding": "derived"}
    # correct result rows, but the prose states a derived figure absent from them
    res = SimpleNamespace(answer="about 3.5 orders per customer",
                          last_result={"columns": ["c"], "rows": [[10]]},
                          stopped="final", trace=[], last_sql="")
    rec = score_result(entry, res)
    assert rec["passed"] is True                    # result_match on the rows
    assert rec["grounded"] is False                 # 3.5 appears in no cell
    assert rec["grounding_false_negative"] is True  # recorded, not counted against passed


def test_score_result_unjoinable_passes_on_degradation():
    entry = {"id": "cd", "domain": "cross-domain", "match_mode": "unjoinable",
             "expected": [], "grounding": "none"}
    res = SimpleNamespace(answer="These are separate domains and cannot be joined.",
                          last_result=None, stopped="final", trace=[], last_sql=None)
    rec = score_result(entry, res)
    assert rec["passed"] is True
    assert rec["grounded"] is None
