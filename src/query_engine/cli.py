"""CLI: ask the DataPulse graph-RAG agent a question."""

from __future__ import annotations

import argparse
import logging
import sys

from src.graph.store.neo4j_store import Neo4jStore
from src.query_engine.agent.adk_agent import ask, build_agent
from src.shared.config import Settings


logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the DataPulse graph-RAG agent")
    parser.add_argument("question", nargs="+", help="Natural-language question to ask")
    parser.add_argument("--model", default=None, help="Override Gemini model (defaults to GEMINI_MODEL or gemini-flash-latest)")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    settings = Settings()

    if not settings.neo4j_uri:
        logger.error("NEO4J_URI is not set. Copy .env.sample to .env and fill it in.")
        return 2
    if not settings.google_api_key:
        logger.error("GOOGLE_API_KEY is not set. Copy .env.sample to .env and fill it in.")
        return 2

    question = " ".join(args.question)
    model = args.model or settings.gemini_model

    with Neo4jStore.from_settings(settings) as store:
        agent = build_agent(store, model=model)
        logger.info("Asking: %s", question)
        answer = ask(agent, question)
        print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
