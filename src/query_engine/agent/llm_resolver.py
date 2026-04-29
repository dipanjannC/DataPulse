"""LLM-driven query resolver backed by Gemini."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.graph.store.networkx_store import NetworkXStore
from src.query_engine.domain.query import Query, QueryResult

load_dotenv()


class LLMResolver:
    """Resolves natural-language queries using Gemini with grounded thinking."""

    def __init__(self, store: NetworkXStore, api_key: str | None = None) -> None:
        self.store = store
        self._client = genai.Client(
            api_key=api_key or os.environ["GEMINI_API_KEY"],
        )
        self._model = "gemini-3.1-pro-preview"
        self._config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
            tools=[types.Tool(googleSearch=types.GoogleSearch())],
        )

    def resolve(self, query: Query) -> QueryResult:
        """Plan and execute graph operations via LLM reasoning.

        Args:
            query: A Query with a natural-language ``question`` in parameters.

        Returns:
            QueryResult with synthesized answer.
        """
        question = query.parameters.get("question", "")
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=question)],
            )
        ]

        response_parts: list[str] = []
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=self._config,
        ):
            if chunk.text:
                response_parts.append(chunk.text)

        return QueryResult(data="".join(response_parts))
