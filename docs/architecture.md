# Architecture

## Bounded Contexts

DataPulse uses Domain-Driven Design with three bounded contexts plus a shared kernel:

1. **sales_data** — Owns the sales domain model (Order, Product, Customer), field-level metadata, controlled vocabularies, and CSV loading into pandas DataFrames.
2. **graph** — Transforms DataFrames into a knowledge graph. Defines node/edge types and persists the graph via NetworkX (default) or Neo4j (optional).
3. **query_engine** — Accepts structured queries or natural-language prompts and resolves them against the graph. Two modes: simple (graph traversal) and agentic (LLM-driven).

## Data Flow

```
CSV  ->  pandas DataFrame  ->  nx.Graph / Neo4j  ->  QueryResult
(sales_data)   (sales_data)        (graph)          (query_engine)
```

## Tech Choices

| Concern | Choice | Rationale |
|---|---|---|
| Graph (default) | NetworkX | Zero infrastructure, good for prototyping |
| Graph (optional) | Neo4j | Production-grade, Cypher queries |
| Agentic queries | LangChain | LLM orchestration with tool use |
