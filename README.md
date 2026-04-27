# DataPulse

Knowledge Graph Based Querying on Sales Data.

## Overview

DataPulse builds a knowledge graph from sales data and exposes two query modes — structured graph traversal and LLM-driven agentic querying — so analysts can explore relationships between orders, products, customers, regions, and channels without writing low-level graph code.

## Domain Contexts

| Domain | Responsibility |
|---|---|
| `sales_data` | Schema metadata, domain models, CSV loading |
| `graph` | Knowledge graph construction, node/edge modeling, persistence |
| `query_engine` | Structured and agentic querying over the graph |
| `shared` | Cross-cutting config and exceptions |

**Data flow:** `sales_data` (DataFrame) &rarr; `graph` (nx.Graph) &rarr; `query_engine` (QueryResult)

## Tech Stack

- **Python** &ge; 3.10
- **pandas** — tabular data handling
- **NetworkX** — in-memory knowledge graph
- **neo4j** *(optional)* — persistent graph database backend
- **langchain** *(optional)* — LLM-powered agentic queries

## Quick Start

```bash
# Install in editable mode
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## Project Structure

```
src/
├── shared/          # Config, exceptions
├── sales_data/      # Domain models, schema metadata, CSV loading
├── graph/           # Graph schema, builder, NetworkX store
└── query_engine/    # Query models, simple resolver, agentic resolver
```

## License

Internal — SnC Labs.
