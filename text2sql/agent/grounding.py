"""Deterministic answer-grounding — a zero-LLM-call sanity signal.

The agent's final ``answer`` is verbatim model text (``agent.py``) and is never
checked against the rows the tools returned, so an answer can silently disagree
with the data while the API still reports success. This module provides a
*deterministic* grounding signal: do the salient numbers the answer states
actually appear in the last SQL result?

It is deliberately **advisory, not a gate** — a wrong hard block would hurt UX
more than a caveat helps. The signal false-negatives on *derived* figures a
correct answer computes but no single cell contains (e.g. "3.5 orders per
customer"), which is exactly why it must not gate. The API surfaces it as an
"unverified against data" caveat; the offline eval harness
(``text2sql.eval.scoring``) reuses ``answer_grounded`` and measures its
false-negative rate against the gold set rather than trusting it blindly.

Grounding checks answer-vs-rows *consistency*, NOT correctness: an answer that
restates a number from a wrong query reads as grounded. Correctness is
``result_match``'s job (against the gold expected value).
"""
from __future__ import annotations

import math
import re

# A number as it appears in prose or a cell: 1,200,000.00 / $7,782,964.89 / 87.3% / -12
_NUMBER = re.compile(r"[-+]?\$?\s*\d[\d,]*(?:\.\d+)?%?")

# Match tolerance. rel_tol absorbs float-summation-order drift on large money
# values (~1e-6 relative); abs_tol gives cent-level slack and covers small
# ratios where rel_tol would be far too tight.
REL_TOL = 1e-6
ABS_TOL = 0.01


def normalize_number(token: object) -> float | None:
    """Parse a value to a float, tolerant of ``$ , %`` and surrounding space.
    Returns None if it is not a number. ``bool`` is treated as non-numeric so
    True/False never compares equal to 1/0."""
    if isinstance(token, bool):
        return None
    if isinstance(token, (int, float)):
        return float(token)
    if not isinstance(token, str):
        return None
    s = token.strip().replace(",", "").replace("$", "").replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def numbers_close(a: float, b: float, *, rel_tol: float = REL_TOL, abs_tol: float = ABS_TOL) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def extract_numbers(text: str) -> list[float]:
    """Salient numbers stated in a natural-language string."""
    out: list[float] = []
    for m in _NUMBER.findall(text or ""):
        v = normalize_number(m)
        if v is not None:
            out.append(v)
    return out


def _result_numbers(last_result: dict | None) -> list[float]:
    if not last_result:
        return []
    nums: list[float] = []
    for row in last_result.get("rows", []) or []:
        cells = row if isinstance(row, (list, tuple)) else [row]
        for cell in cells:
            v = normalize_number(cell)
            if v is not None:
                nums.append(v)
    return nums


def answer_grounded(answer: str, last_result: dict | None) -> bool:
    """True iff the answer is consistent with the last SQL result.

    - No SQL result / no rows -> not grounded (nothing backs the prose).
    - Answer states no numbers -> grounded (a non-empty answer over real rows has
      no numeric claim to diverge from the data).
    - Answer states numbers -> grounded iff *at least one* matches a numeric cell
      (within tolerance). "At least one" is deliberate: prose carries incidental
      numbers (a "Q4", a year, a "top 5") that are not the answer's figure, so
      requiring all to match would flag correct answers. The signal fires only
      when the stated numbers appear *nowhere* in the rows — a strong, low-noise
      indication the prose left the data behind.
    """
    if not last_result or not last_result.get("rows"):
        return False
    ans_nums = extract_numbers(answer or "")
    if not ans_nums:
        return bool((answer or "").strip())
    result_nums = _result_numbers(last_result)
    return any(numbers_close(a, r) for a in ans_nums for r in result_nums)


def check_grounding(answer: str, last_result: dict | None) -> dict:
    """Advisory grounding verdict for the API layer: ``{"grounded", "reason"}``.

    ``grounded=False`` means the answer's stated figures were not found in the
    last SQL result (or there was no result) and the UI should show an
    "unverified against data" caveat. It never blocks or hides the answer."""
    if last_result is None:
        return {"grounded": False, "reason": "No SQL result backs this answer."}
    if not last_result.get("rows"):
        return {"grounded": False, "reason": "The last query returned no rows to support this answer."}
    if answer_grounded(answer, last_result):
        return {"grounded": True, "reason": "The answer's figures match the query results."}
    return {"grounded": False, "reason": "The answer's figures were not found in the query results."}
