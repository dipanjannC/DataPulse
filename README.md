# DataPulse

Knowledge Graph Based Querying on Sales Data.

## Overview

DataPulse builds a knowledge graph from sales data and exposes two query modes — structured graph traversal and LLM-driven agentic querying — so analysts can explore relationships between orders, products, customers, regions, and channels without writing low-level graph code.

## Text2SQL stack (`text2sql/`) — the active NL-to-SQL app

The natural-language-to-SQL application lives under **[`text2sql/`](text2sql/README.md)**: a
Groq-backed agent that plans queries by calling tools over a Neo4j knowledge graph of the
schema, then runs read-only SQL against SQLite — spanning Sales, IT, HR, Marketing, and
Security data. It is standalone (imports nothing from `src/`, deploys via `render.yaml`) and
organized into four layers: **Generate → Quality → Load → Consume**.

**Start here: [`text2sql/README.md`](text2sql/README.md)** — architecture, how to run the
pipeline, how to add a new domain, and how the agent answers a question.

```bash
uv run python text2sql/pipeline.py                 # generate → validate → SQLite + Neo4j KG
uv run uvicorn text2sql.api.main:app --port 8000   # then open http://localhost:8000/
```

> The `src/` sections below describe an earlier graph-querying stack and are partly out of
> date (the NetworkX/langchain query modes were removed). New work happens in `text2sql/`.

## Domain Contexts

| Domain | Responsibility |
|---|---|
| `sales_data` | Schema metadata, domain models, CSV loading |
| `graph` | Knowledge graph construction, node/edge modeling, persistence |
| `query_engine` | Structured and agentic querying over the graph |
| `shared` | Cross-cutting config and exceptions |

**Data flow:** `sales_data` (DataFrame) &rarr; `graph` (Neo4j) &rarr; `query_engine` (QueryResult)

## Tech Stack

- **Python** &ge; 3.10
- **uv** — package & environment manager
- **pandas** — tabular data handling
- **neo4j** — persistent graph database backend

## Quick Start

This project uses [`uv`](https://docs.astral.sh/uv/) as its package manager.

```bash
# Sync dependencies (creates .venv and installs dev extras)
uv sync --extra dev

# Run tests
uv run pytest tests/
```

## Project Structure

```
src/
├── shared/          # Config, exceptions
├── sales_data/      # Domain models, schema metadata, CSV loading
├── graph/           # Graph schema, builder, NetworkX store
└── query_engine/    # Query models, CLI, ADK agent
```

## License

Internal — SnC Labs.
