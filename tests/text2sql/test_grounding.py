"""Tests for the deterministic answer-grounding signal.

Grounding is advisory: it flags an answer whose stated figures appear nowhere in
the rows. It checks answer-vs-rows *consistency*, not correctness. The known
false-negative on *derived* values is asserted here so the harness measures it
honestly rather than hiding it.
"""
from __future__ import annotations

from text2sql.agent.grounding import (
    answer_grounded,
    check_grounding,
    extract_numbers,
    normalize_number,
)


# ── number parsing ──────────────────────────────────────────────────────────

def test_normalize_number_tolerates_currency_commas_percent():
    assert normalize_number("$7,782,964.89") == 7782964.89
    assert normalize_number("87.3%") == 87.3
    assert normalize_number(5) == 5.0
    assert normalize_number("not a number") is None
    assert normalize_number(True) is None  # bool is not a numeric cell


def test_extract_numbers_pulls_salient_figures():
    assert extract_numbers("Revenue was $7,782,964.89 across 2,000 orders") == [7782964.89, 2000.0]
    assert extract_numbers("no numbers here") == []


# ── grounded vs ungrounded ──────────────────────────────────────────────────

def test_grounded_when_stated_number_appears_in_rows():
    assert answer_grounded("Total revenue is 7,782,964.89.", {"rows": [[7782964.89]]})


def test_grounded_tolerant_of_formatting_and_rounding():
    assert answer_grounded("Revenue is $7,782,964.89.", {"rows": [[7782964.8900012]]})


def test_ungrounded_when_stated_number_absent_from_rows():
    # the answer claims the invoices figure, but the rows hold the line-item total
    assert not answer_grounded("Revenue is 2,030,281.53.", {"rows": [[7782964.89]]})


def test_incidental_prose_numbers_do_not_break_grounding():
    # "Q4" and a year are incidental; the real figure matches, so it is grounded
    assert answer_grounded("In Q4 2024 revenue reached 7,782,964.89.",
                           {"rows": [[7782964.89]]})


def test_derived_value_reads_as_ungrounded_known_false_negative():
    # a correct derived figure that appears in no cell — the documented, measured
    # false-negative that is exactly why grounding is advisory, never a gate
    assert not answer_grounded("About 3.5 orders per customer.",
                               {"rows": [[2000], [573]]})


def test_answer_without_numbers_is_grounded_over_real_rows():
    assert answer_grounded("Here are the matching records.", {"rows": [[1]]})


def test_no_rows_is_never_grounded():
    assert not answer_grounded("Revenue is 5.", {"rows": []})
    assert not answer_grounded("Revenue is 5.", None)


# ── check_grounding wrapper (API-facing verdict) ────────────────────────────

def test_check_grounding_reports_reason_for_each_case():
    ok = check_grounding("Revenue is 7,782,964.89.", {"rows": [[7782964.89]]})
    assert ok["grounded"] is True and "match" in ok["reason"].lower()

    no_sql = check_grounding("Revenue is 5.", None)
    assert no_sql["grounded"] is False and "no sql result" in no_sql["reason"].lower()

    empty = check_grounding("Revenue is 5.", {"rows": []})
    assert empty["grounded"] is False and "no rows" in empty["reason"].lower()

    diverged = check_grounding("Revenue is 2,030,281.53.", {"rows": [[7782964.89]]})
    assert diverged["grounded"] is False and "not found" in diverged["reason"].lower()
