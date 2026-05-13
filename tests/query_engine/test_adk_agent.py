"""Tests for adk agent assembly. Runner is exercised via mocks."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.query_engine.agent import adk_agent, schema_card


class _FakeStore:
    def run_read(self, query: str, **_params):
        return [{"answer": 42}]


def test_build_agent_uses_schema_card():
    agent = adk_agent.build_agent(_FakeStore())
    assert agent.instruction == schema_card.SCHEMA_CARD


def test_build_agent_registers_run_cypher_tool():
    agent = adk_agent.build_agent(_FakeStore())
    tool_names = [getattr(t, "__name__", getattr(t, "name", "")) for t in agent.tools]
    assert any("run_cypher" in name for name in tool_names)


def test_build_agent_picks_up_model_override():
    agent = adk_agent.build_agent(_FakeStore(), model="gemini-pro-test")
    assert agent.model == "gemini-pro-test"


def test_tool_calls_through_to_cypher_tool():
    store = _FakeStore()
    agent = adk_agent.build_agent(store)
    tool_callable = agent.tools[0]
    out = tool_callable("MATCH (n) RETURN n LIMIT 1")
    assert out["rows"] == [{"answer": 42}]


def test_ask_invokes_runner_async(monkeypatch):
    captured = {}

    async def fake_ask_async(agent, question):
        captured["agent"] = agent
        captured["question"] = question
        return "stub answer"

    with patch("src.query_engine.agent.adk_agent._ask_async", side_effect=fake_ask_async):
        agent = adk_agent.build_agent(_FakeStore())
        out = adk_agent.ask(agent, "How many orders?")
    assert out == "stub answer"
    assert captured["question"] == "How many orders?"
    assert captured["agent"] is agent
