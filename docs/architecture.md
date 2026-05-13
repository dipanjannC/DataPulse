# Architecture

## Bounded Contexts

DataPulse uses Domain-Driven Design with three bounded contexts plus a shared kernel and a datagen module:

1. **sales_data** — Owns the sales domain model (Order, Product, Customer), field-level metadata, and controlled vocabularies (Region, Channel, ProductCategory).
2. **graph** — Loads sales CSVs directly into Neo4j as a knowledge graph. Defines node labels / relationship types (`schema.py`), the driver wrapper (`Neo4jStore`), and the CSV → graph loader (`Neo4jGraphBuilder`).
3. **query_engine** — A single google-adk `Agent` answers natural-language questions by calling a read-only `run_cypher` tool against Neo4j.
4. **datagen** — Generates synthetic sales CSVs (`src/datagen/`) for testing and demos.

## Data Flow

```
CSV  ->  Neo4j (Aura)  ->  google-adk Agent + run_cypher tool  ->  natural-language answer
(datagen / data/raw)    (graph)                                   (query_engine)
```

## Tech Choices

| Concern | Choice | Rationale |
|---|---|---|
| Knowledge graph | Neo4j (managed Aura) | Production-grade; Cypher; no local infra |
| Agent framework | google-adk | Native Gemini support; simple function-tool API; sync + async runners |
| LLM | Gemini (via google-adk → google-genai) | Same API key powers both adk and direct genai calls if needed |
| CSV → graph | `Neo4jGraphBuilder` with UNWIND-batched MERGE | Idempotent reloads; efficient over the Bolt protocol |

## Import Rules (DDD)

- `sales_data` MUST NOT import from `graph` or `query_engine`.
- `graph` MAY import `sales_data` domain models.
- `query_engine` MAY import `graph` and `sales_data` domain models.
- `datagen` MAY import `sales_data` (no other contexts).
- All MAY import from `shared`.
