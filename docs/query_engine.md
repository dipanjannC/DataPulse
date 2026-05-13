# Query Engine

## How questions become answers

DataPulse uses a single google-adk `Agent` for all queries. The agent is given:

1. A **schema card** as its system instruction — node labels with properties, the five relationship types, and the canonical Region / Channel / Category values. Generated from the enums in `src/graph/domain/schema.py` and `src/sales_data/metadata/enums.py` so it stays in sync.
2. One **function tool**: `run_cypher(query: str) -> dict`. The agent decides what to ask, writes Cypher, and reads the rows back.

## Flow

```
natural-language question
   │
   ▼
google-adk Agent (Gemini)
   │   plans a read query
   ▼
run_cypher tool ──► Neo4jStore.run_read ──► Neo4j Aura
   │                                          │
   │                  rows  ◄─────────────────┘
   ▼
Agent reads rows, may call run_cypher again, then writes the final natural-language answer.
```

## Read-only guard

`run_cypher` rejects any query containing (case-insensitive, word-bounded):

`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`, `REMOVE`, `DETACH`, `LOAD CSV`, `CALL apoc.*`, `CALL db.*`, `CALL dbms.*`

Rejection returns a structured error the agent can react to (it'll typically reformulate). Comments are stripped before checking, so a property literally named `create_date` doesn't trip the guard.

Result rows are capped at 100; `truncated_at` is set when the cap is hit, signaling the agent to aggregate rather than list.

## Calling from code

```python
from src.shared.config import Settings
from src.graph.store.neo4j_store import Neo4jStore
from src.query_engine.agent.adk_agent import build_agent, ask

with Neo4jStore.from_settings(Settings()) as store:
    agent = build_agent(store)
    print(ask(agent, "What are the top 3 product categories by total quantity?"))
```

## Calling from CLI

```
uv run python -m src.query_engine.cli "How many orders shipped to Europe in Q1 2024?"
```

`Settings` reads `GOOGLE_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and optionally `GEMINI_MODEL` from `.env` (see `.env.sample`).
