"""Tests for the externalized, configurable system prompt.

The prompt template lives outside the agent so it can be tuned per deployment
without a code change; these lock the resolution order (explicit path -> env var
-> bundled file -> fallback), the brace-safe substitution, and that externalizing
kept the grounding hardening.
"""
from __future__ import annotations

import logging

import text2sql.agent.prompt as prompt
from text2sql.agent.prompt import (
    ENV_VAR,
    build_system_prompt,
    load_prompt_template,
)


# ── {domains} substitution ──────────────────────────────────────────────────

def test_build_system_prompt_fills_domains_marker():
    out = build_system_prompt(["Sales", "IT"], template="spanning {domains}.")
    assert out == "spanning Sales, and IT data."


def test_build_system_prompt_absorbs_a_new_domain_without_template_edits():
    out = build_system_prompt(["Sales", "Logistics"], template="over {domains}")
    assert "Sales, and Logistics data" in out


def test_build_system_prompt_falls_back_phrase_when_no_domains():
    assert "multiple business domains" in build_system_prompt([], template="{domains}")


def test_build_system_prompt_is_brace_safe():
    # a business-edited prompt may contain literal { } (e.g. a JSON few-shot);
    # only the {domains} marker is substituted, other braces are left intact.
    tmpl = 'Answer {domains}. Example row: {"revenue": 10}'
    out = build_system_prompt(["Sales"], template=tmpl)
    assert out == 'Answer Sales data. Example row: {"revenue": 10}'


# ── resolution order ─────────────────────────────────────────────────────────

def test_load_prefers_explicit_path(tmp_path, monkeypatch):
    f = tmp_path / "custom.txt"
    f.write_text("CUSTOM {domains}", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "env.txt"))  # would lose to the explicit path
    assert load_prompt_template(f) == "CUSTOM {domains}"


def test_load_uses_env_var_when_no_explicit_path(tmp_path, monkeypatch):
    f = tmp_path / "env.txt"
    f.write_text("FROM ENV {domains}", encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(f))
    assert load_prompt_template() == "FROM ENV {domains}"


def test_load_uses_bundled_default_when_unconfigured(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    text = load_prompt_template()
    # the bundled default carries the tool contract and the grounding hardening
    assert "get_schema_context" in text
    assert "Base the final answer ONLY on the rows" in text


def test_load_falls_back_when_all_sources_missing(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(prompt, "BUNDLED_PROMPT", tmp_path / "does_not_exist.txt")
    assert load_prompt_template(tmp_path / "also_missing.txt") == prompt._FALLBACK_TEMPLATE


# ── hardening: silent-degradation modes must warn ───────────────────────────

def test_fallback_to_in_code_default_warns_loudly(tmp_path, monkeypatch, caplog):
    # a missing bundled file in a deploy means the configured prompt is NOT in
    # effect — that must be visible, not silent.
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(prompt, "BUNDLED_PROMPT", tmp_path / "missing.txt")
    with caplog.at_level(logging.WARNING):
        out = load_prompt_template()
    assert out == prompt._FALLBACK_TEMPLATE
    assert "NOT in effect" in caplog.text


def test_configured_template_without_domains_marker_warns(tmp_path, caplog):
    # a business-edited prompt that drops {domains} loses the domain injection —
    # warn the author rather than silently shipping a marker-less prompt.
    f = tmp_path / "nomarker.txt"
    f.write_text("A prompt with no marker at all.", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        out = load_prompt_template(f)
    assert out == "A prompt with no marker at all."
    assert "no {domains} marker" in caplog.text


def test_valid_template_does_not_warn(tmp_path, caplog):
    f = tmp_path / "ok.txt"
    f.write_text("Fine prompt over {domains}.", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        load_prompt_template(f)
    assert caplog.text == ""


def test_env_pointing_at_missing_file_falls_through_to_bundled(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "nope.txt"))
    # unreadable env file -> fall through to the bundled default (still functional)
    assert "get_schema_context" in load_prompt_template()


# ── the bundled default is what the agent uses by default ────────────────────

def test_default_build_uses_bundled_prompt_and_fills_domains(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    out = build_system_prompt(["Sales", "IT", "HR", "Marketing", "Security"])
    assert "Sales, IT, HR, Marketing, and Security data" in out
    assert "never use invoices.amount for revenue" in out  # metric-disambiguation rule survived
