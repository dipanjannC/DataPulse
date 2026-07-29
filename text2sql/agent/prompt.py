"""System-prompt configuration.

The agent's instructions live *outside* the loop so they can be tuned per
deployment / business standards without a code change. The DI'd `run_agent`
already accepts a `system_prompt` string; this module is how that string is
sourced and how a new prompt is *utilized* — point an env var (or an explicit
path) at a file, or edit the bundled default; no code edit required.

Resolution order (first that yields non-empty text wins):
  1. an explicit ``path`` argument,
  2. the ``DATAPULSE_SYSTEM_PROMPT_PATH`` env var (a file path),
  3. the bundled default, ``prompts/system_prompt.txt`` (edit this to change the
     default prompt),
  4. a compact in-code fallback, so a missing/unreadable file never breaks the
     agent (a degraded but functional prompt, logged when it happens).

The template carries a literal ``{domains}`` marker filled at wiring time by
``build_system_prompt``. Substitution is a plain ``str.replace`` (not
``str.format``) so a business-edited prompt may contain literal ``{ }`` — e.g.
JSON in a few-shot example — without escaping.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DOMAINS_MARKER = "{domains}"
ENV_VAR        = "DATAPULSE_SYSTEM_PROMPT_PATH"
BUNDLED_PROMPT = Path(__file__).parent / "prompts" / "system_prompt.txt"

# Safety net used ONLY if no prompt file can be read. The authoritative default
# is prompts/system_prompt.txt — edit that (or point ENV_VAR at your own file)
# rather than this constant.
_FALLBACK_TEMPLATE = (
    "You are DataPulse, an analyst that answers business questions by querying a "
    "SQLite database spanning {domains}. Call tools to discover the schema, exact "
    "join keys, and canonical metric definitions before writing SQL; never guess "
    "table or column names. Use only read-only SELECT/WITH queries. Base the final "
    "answer only on the rows your last run_sql call returned, restate the exact "
    "figures from them, and say so plainly if no result supports the claim."
)


def load_prompt_template(path: str | Path | None = None) -> str:
    """Resolve the system-prompt template text (see the module docstring for the
    resolution order). Always returns non-empty text."""
    for source, candidate in (("path", path),
                              ("env", os.getenv(ENV_VAR)),
                              ("bundled", BUNDLED_PROMPT)):
        if not candidate:
            continue
        try:
            text = Path(candidate).read_text(encoding="utf-8").strip()
        except OSError:
            # An explicitly requested prompt that can't be read is worth flagging;
            # a missing bundled file just falls through to the in-code fallback.
            if source in ("path", "env"):
                logger.warning("system-prompt file %r is unreadable; falling back", str(candidate))
            continue
        if text:
            return text
    return _FALLBACK_TEMPLATE


def _domains_phrase(domains: list[str]) -> str:
    names = [d for d in domains if d]
    if not names:
        return "multiple business domains"
    if len(names) == 1:
        return f"{names[0]} data"
    return ", ".join(names[:-1]) + f", and {names[-1]} data"


def build_system_prompt(domains: list[str], *, template: str | None = None) -> str:
    """Fill the template's ``{domains}`` marker with the catalog's domain list, so
    a new domain needs no prompt edit. ``template`` overrides the configured
    source (used by tests and programmatic callers); otherwise the template is
    resolved via ``load_prompt_template``."""
    tmpl = template if template is not None else load_prompt_template()
    return tmpl.replace(DOMAINS_MARKER, _domains_phrase(domains))
