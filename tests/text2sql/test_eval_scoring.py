"""The ruler's own test — the trust anchor of the eval harness.

`result_match` must accept a *right answer in the wrong shape* and reject a
*wrong answer*. If it did the reverse it would mis-order every downstream fix, so
these adversarial same-answer/different-SQL-shape pairs are what make the eval
report trustworthy. Pure, no services.
"""
from __future__ import annotations

from text2sql.eval.scoring import (
    answer_signals_unjoinable,
    flatten_cells,
    result_match,
    score_unjoinable,
)


# ── same answer, different SQL shape → MUST match ───────────────────────────

def test_column_name_or_alias_is_ignored():
    # `AS revenue` vs `AS total_revenue` — the label must not matter
    assert result_match([1200000.0], {"columns": ["total_revenue"], "rows": [[1200000.0]]})
    assert result_match([1200000.0], {"columns": ["revenue"], "rows": [[1200000.0]]})


def test_float_formatting_is_equivalent():
    # 1200000.0 vs 1200000.00 vs integer 1200000
    assert result_match([1200000.0], {"rows": [[1200000.00]]})
    assert result_match([1200000.0], {"rows": [[1200000]]})


def test_integer_vs_real_match():
    assert result_match([5], {"rows": [[5.0]]})
    assert result_match([5.0], {"rows": [[5]]})


def test_extra_grouping_column_is_tolerated():
    # expected the scalar total; actual carries an extra grouping label column
    assert result_match([1200000.0], {"columns": ["tier", "rev"], "rows": [["Gold", 1200000.0]]})


def test_scalar_vs_single_labeled_row():
    assert result_match(2000, {"columns": ["c"], "rows": [[2000]]})


def test_money_cent_rounding_within_tolerance():
    # float-summation drift on a large sum must still read as the same money value
    assert result_match([7782964.89], {"rows": [[7782964.8900012]]})


def test_string_target_is_case_and_space_insensitive():
    assert result_match(["Ana Acosta"], {"rows": [["ana acosta"]]})
    assert result_match(["Gold"], {"columns": ["tier"], "rows": [["  GOLD  "]]})


def test_row_order_does_not_matter():
    assert result_match([1, 2, 3], {"rows": [[3], [1], [2]]}, mode="set")


def test_mixed_number_and_label_target():
    assert result_match(["Ana Acosta", 56061.31],
                        {"columns": ["name", "rev"], "rows": [["Ana Acosta", 56061.31]]})


# ── wrong answer → MUST fail (a ruler that passes everything is useless) ────

def test_wrong_number_fails():
    # the revenue trap: order_items.line_total (7.78M) vs invoices.amount (2.03M)
    assert not result_match([7782964.89], {"rows": [[2030281.53]]})


def test_missing_one_of_several_targets_fails():
    assert not result_match([10, 20], {"rows": [[10]]})


def test_multiset_requires_distinct_cells():
    # two expected 10s need two actual 10s, not one reused twice
    assert not result_match([10, 10], {"rows": [[10]]})
    assert result_match([10, 10], {"rows": [[10], [10]]})


def test_empty_or_missing_result_fails():
    assert not result_match([5], {"rows": []})
    assert not result_match([5], None)
    assert not result_match([5], {"columns": ["c"], "rows": []})


def test_set_mode_rejects_extra_or_missing():
    assert not result_match([1, 2, 3], {"rows": [[1], [2]]})           # missing 3
    assert not result_match([1, 2, 3], {"rows": [[1], [2], [3], [4]]}, mode="set")  # extra 4
    assert result_match([1, 2, 3], {"rows": [[1], [2], [3]]}, mode="set")


def test_contains_allows_extra_rows_but_set_does_not():
    actual = {"rows": [[1], [2], [3], [4]]}
    assert result_match([1, 2], actual)                 # containment ok
    assert not result_match([1, 2], actual, mode="set")  # not full equality


# ── flatten_cells shapes ────────────────────────────────────────────────────

def test_flatten_cells_accepts_dict_rows_and_flat_lists():
    assert flatten_cells({"rows": [[1, 2], [3]]}) == [1, 2, 3]
    assert flatten_cells([[1, 2], [3]]) == [1, 2, 3]
    assert flatten_cells([1, 2, 3]) == [1, 2, 3]
    assert flatten_cells(None) == []


# ── cross-domain "not joinable" (degradation, not containment) ──────────────

def test_answer_signals_unjoinable_detects_refusal_phrases():
    assert answer_signals_unjoinable("These tables are in separate domains and cannot be joined.")
    assert answer_signals_unjoinable("There is no defined join key between them.")
    assert not answer_signals_unjoinable("The total revenue is 7,782,964.89.")


def test_score_unjoinable_passes_on_graceful_degradation():
    # no rows produced -> the agent never fabricated a cross-domain join
    assert score_unjoinable("I could not find a link.", {"rows": []})
    assert score_unjoinable("anything", None)
    # rows produced but the answer explicitly says not joinable
    assert score_unjoinable("These are separate domains and cannot be joined.",
                            {"rows": [[1]]})


def test_score_unjoinable_fails_when_a_join_is_fabricated():
    # rows returned AND the answer asserts a joined number with no refusal signal
    assert not score_unjoinable("The joined total is 42.", {"rows": [[42]]})
