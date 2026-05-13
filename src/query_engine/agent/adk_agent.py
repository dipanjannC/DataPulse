"""google-adk Agent that answers sales questions via Cypher tool calls."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from src.query_engine.agent import cypher_tool, schema_card


logger = logging.getLogger(__name__)


def _make_run_cypher(store: Any) -> Callable[[str], dict]:
    def run_cypher(query: str) -> dict:
        """Execute a read-only Cypher query against the sales knowledge graph.

        Args:
            query: A read-only Cypher query string (MATCH/RETURN/WITH/UNWIND).

        Returns:
            A dict with `rows` (list of result records) and optional `error`.
        """
        return cypher_tool.run_cypher(query, store)

    return run_cypher


def build_agent(store: Any, *, model: str = "gemini-flash-latest", name: str = "datapulse_graph_rag") -> Agent:
    return Agent(
        name=name,
        model=model,
        instruction=schema_card.SCHEMA_CARD,
        tools=[_make_run_cypher(store)],
    )


async def _ask_async(agent: Agent, question: str) -> str:
    runner = Runner(
        app_name=agent.name,
        agent=agent,
        session_service=InMemorySessionService(),
    )
    user_id = "datapulse_user"
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    await runner.session_service.create_session(
        app_name=agent.name,
        user_id=user_id,
        session_id=session_id,
    )
    message = genai_types.Content(role="user", parts=[genai_types.Part(text=question)])

    final_text: str | None = None
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts)
    return final_text or ""


def ask(agent: Agent, question: str) -> str:
    """Synchronous wrapper around the agent's async runner."""
    return asyncio.run(_ask_async(agent, question))
