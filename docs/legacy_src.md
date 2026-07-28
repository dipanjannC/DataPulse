# Legacy stack (`src/`) — reference only

> **Status: legacy / retired.** The active stack under `src/` + `text2sql/agent/` is the single path forward (see
> [architecture.md](architecture.md)). This file preserves the documentation for the older
> `src/` graph-querying stack — a *different* system: sales-only, data loaded **into** Neo4j,
> answered by a google-adk **Gemini** agent writing **Cypher**. It is kept for reference while
> `src/` still exists; `src/datagen` in particular remains a harvest source. New work does not
> go here.

---

## Architecture (src)

### Bounded contexts

DataPulse's `src/` stack uses Domain-Driven Design with three bounded contexts plus a shared kernel and a datagen module:

1. **sales_data** — Owns the sales domain model (Order, Product, Customer), field-level metadata, and controlled vocabularies (Region, Channel, ProductCategory).
2. **graph** — Loads sales CSVs directly into Neo4j as a knowledge graph. Defines node labels / relationship types (`schema.py`), the driver wrapper (`Neo4jStore`), and the CSV → graph loader (`Neo4jGraphBuilder`).
3. **query_engine** — A single google-adk `Agent` answers natural-language questions by calling a read-only `run_cypher` tool against Neo4j.
4. **datagen** — Generates synthetic sales CSVs (`src/datagen/`) for testing and demos.

### Data flow

```
CSV  ->  Neo4j (Aura)  ->  google-adk Agent + run_cypher tool  ->  natural-language answer
(datagen / data/raw)    (graph)                                   (query_engine)
```

### Import rules (DDD)

- `sales_data` MUST NOT import from `graph` or `query_engine`.
- `graph` MAY import `sales_data` domain models.
- `query_engine` MAY import `graph` and `sales_data` domain models.
- `datagen` MAY import `sales_data` (no other contexts).
- All MAY import from `shared`.

---

## Data model (src)

### Sales entities

| Entity | Key Fields |
|---|---|
| **Order** | order_id, customer_id, product_id, quantity, unit_price, order_date, region, channel |
| **Product** | product_id, product_name, category |
| **Customer** | customer_id, customer_name |
| **Region** | name (e.g. North America, Europe, Asia Pacific) |
| **Channel** | name (e.g. Online, Retail, Distributor) |
| **Category** | name (e.g. Electronics, Stationery, Furniture) |

### Neo4j mapping

Node labels and relationship types are the canonical Cypher strings — defined once in `src/graph/domain/schema.py` and reused by the builder, the agent's schema card, and the tests.

**Node labels:** `Customer` (key `customer_id`), `Order` (`order_id`), `Product` (`product_id`), `Region` (`name`), `Channel` (`name`), `Category` (`name`).

**Relationships:**

- `(Customer)-[:PLACED]->(Order)`
- `(Order)-[:CONTAINS]->(Product)`
- `(Order)-[:IN_REGION]->(Region)`
- `(Order)-[:VIA_CHANNEL]->(Channel)`
- `(Product)-[:BELONGS_TO]->(Category)`

Constraints are created on first load by `Neo4jStore.setup_constraints()` (one UNIQUE per label key). The loader uses `MERGE` for nodes and relationships, so re-running on the same CSV is idempotent.

---

## Query engine (src)

A single google-adk `Agent` answers all queries. It is given a **schema card** (system
instruction generated from the graph enums) and one **function tool**: `run_cypher(query) -> dict`.
The agent writes Cypher, reads rows, and may iterate before answering.

```
natural-language question -> google-adk Agent (Gemini) -> run_cypher -> Neo4jStore.run_read -> Neo4j Aura
                                                              rows back -> Agent -> final answer
```

**Read-only guard:** `run_cypher` rejects (case-insensitive, word-bounded, comment-stripped)
`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`, `REMOVE`, `DETACH`, `LOAD CSV`, `CALL apoc.*`,
`CALL db.*`, `CALL dbms.*`. Result rows are capped at 100 (`truncated_at` signals the cap).

**Calling from CLI:** `uv run python -m src.query_engine.cli "..."`. `Settings` reads
`GOOGLE_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and optional `GEMINI_MODEL`.
