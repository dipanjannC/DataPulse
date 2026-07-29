"""Deterministic scoring for the eval harness — the *ruler*.

Two independent measures, kept separate on purpose:

- ``result_match(expected, actual)`` — the PRIMARY accuracy metric. A tolerant
  value-*multiset containment* check, NOT set-equality: it rounds floats,
  strips ``$ , %``, ignores column names/aliases and row order, and (by default)
  asserts the expected target value(s) *appear* in the result rather than
  demanding full result-set identity. A ruler that flagged a right answer in the
  wrong shape (``AS revenue`` vs ``AS total_revenue``, ``1200000.0`` vs
  ``1200000.00``, INTEGER-vs-REAL, an extra grouping column, scalar-vs-single-row)
  as wrong would mis-order every downstream fix — a ruler that reports right
  answers as wrong is worse than no ruler — so those must all read as matches.

- ``answer_grounded`` (re-exported from ``text2sql.agent.grounding``) — a
  DIAGNOSTIC signal only, never folded into the pass-rate: it false-negatives on
  derived values. The harness reports its false-negative rate; it does not gate.

- ``score_unjoinable`` — the cross-domain "not joinable" case has no numeric
  target, so it is scored on graceful degradation (no fabricated join answer),
  kept out of the containment path entirely.

Pure and unit-tested with adversarial fakes (tests/text2sql/test_eval_scoring.py).
"""
from __future__ import annotations

from text2sql.agent.grounding import answer_grounded, normalize_number, numbers_close

__all__ = [
    "result_match",
    "score_unjoinable",
    "answer_signals_unjoinable",
    "answer_grounded",
    "flatten_cells",
]


def flatten_cells(actual: object) -> list:
    """Every cell value of a result, order- and column-name-agnostic. Accepts a
    ``run_sql`` dict ``{"rows": [...]}``, a list of rows, or a flat list."""
    if actual is None:
        return []
    rows = actual.get("rows", []) if isinstance(actual, dict) else actual
    cells: list = []
    for row in rows or []:
        if isinstance(row, (list, tuple)):
            cells.extend(row)
        else:
            cells.append(row)
    return cells


def _norm(v: object) -> tuple[str, object]:
    """Tag a value for comparison: numeric (tolerant) vs string (case/space
    folded) vs none, so ``5`` and ``5.0`` and ``"5"`` compare equal while
    ``"Gold"`` stays a string."""
    if v is None:
        return ("none", None)
    n = normalize_number(v)
    if n is not None:
        return ("num", n)
    return ("str", str(v).strip().lower())


def _values_equal(a: tuple[str, object], b: tuple[str, object]) -> bool:
    ta, va = a
    tb, vb = b
    if ta == "num" and tb == "num":
        return numbers_close(va, vb)  # type: ignore[arg-type]
    return (ta, va) == (tb, vb)


def _multiset_contains(expected: list, cells: list) -> bool:
    """True iff every expected value matches a DISTINCT actual cell (so
    ``[10, 10]`` needs two matching cells, not one)."""
    remaining = list(cells)
    for e in expected:
        hit = next((i for i, c in enumerate(remaining) if _values_equal(e, c)), None)
        if hit is None:
            return False
        remaining.pop(hit)
    return True


def result_match(expected: object, actual: object, *, mode: str = "contains") -> bool:
    """Does ``actual`` (a run_sql result dict / rows / cells) satisfy ``expected``?

    ``expected`` is a single value or a list of salient target values.

    - ``mode="contains"`` (default): every expected value appears in the result
      as a distinct cell (subset multiset), ignoring extra columns/rows, column
      names, and order. This is what makes ``AS revenue`` vs ``AS total_revenue``
      and an extra grouping column read as matches.
    - ``mode="set"``: full multiset equality of expected vs all result cells.
    """
    exp_list = list(expected) if isinstance(expected, (list, tuple)) else [expected]
    exp = [_norm(v) for v in exp_list]
    cells = [_norm(v) for v in flatten_cells(actual)]

    if mode == "contains":
        return _multiset_contains(exp, cells)
    if mode == "set":
        return len(exp) == len(cells) and _multiset_contains(exp, cells)
    raise ValueError(f"unknown match mode {mode!r}")


# ── cross-domain "not joinable" scoring (degradation, not containment) ──────────

_UNJOINABLE_SIGNALS = (
    "cannot be joined", "can't be joined", "cannot join", "can't join",
    "no defined join", "no join key", "no join path", "no way to join",
    "not joinable", "cannot be linked", "separate domains", "different domains",
    "aren't linked", "are not linked", "not linked", "no relationship",
    "no direct relationship", "no foreign key", "no common key", "no shared key",
    "answer each part separately", "unrelated",
)


def answer_signals_unjoinable(answer: str) -> bool:
    """True iff the answer explicitly states the tables cannot be joined."""
    low = (answer or "").lower()
    return any(sig in low for sig in _UNJOINABLE_SIGNALS)


def score_unjoinable(answer: str, last_result: dict | None) -> bool:
    """Pass a cross-domain gold question on graceful degradation: the agent must
    NOT fabricate a cross-domain join. It passes iff it produced no result rows
    (never invented a joined answer) OR it stated the tables cannot be joined."""
    no_rows = last_result is None or not last_result.get("rows")
    return no_rows or answer_signals_unjoinable(answer)
