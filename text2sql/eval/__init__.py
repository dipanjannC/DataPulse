"""Offline/live accuracy eval harness for the DataPulse SQL agent.

`scoring.py` is the ruler (a tolerant result comparator + a re-exported grounding
signal); `run_eval.py` drives `run_agent` over `gold_questions.jsonl` and reports
per-domain pass-rate. See `run_eval.py` for the CLI.
"""
