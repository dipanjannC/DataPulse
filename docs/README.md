# DataPulse docs

This repo has two stacks:

- **`text2sql/` — the active application** (natural-language → SQL over a schema knowledge graph;
  5 domains; Groq + SQLite + Neo4j). All docs here describe this stack.
- **`src/` — a legacy graph-querying stack**, being retired. Preserved in
  [legacy_src.md](legacy_src.md); `src/datagen` remains a harvest source.

## Start here

New to the project? Read in this order:

1. **[architecture.md](architecture.md)** — the four layers (Generate → Quality → Load → Consume),
   the data flow, and why there are two databases.
2. **[data_model.md](data_model.md)** — the `schema.json` contract, the 5 domains × 10 tables, the
   40 FK edges, the metric glossary, and the SQLite + Neo4j mappings.
3. **[query_engine.md](query_engine.md)** — how a question becomes SQL: the agent loop, its three
   KG-backed tools, the read-only guard, and the HTTP surface.
4. **[quality.md](quality.md)** — what the validation gate checks and how to run it.

Want to *run it or extend it* rather than understand the internals? Go straight to the
task-oriented guide: **[`../text2sql/README.md`](../text2sql/README.md)** (quickstart + how to add
a new domain).

## Map

| Doc | What it answers |
|---|---|
| [architecture.md](architecture.md) | How is the system structured? What talks to what? |
| [data_model.md](data_model.md) | What are the tables, columns, FKs, and metrics? |
| [query_engine.md](query_engine.md) | How is a question answered? What's the API? |
| [quality.md](quality.md) | How is generated data validated, and how does the gate behave? |
| [`../text2sql/README.md`](../text2sql/README.md) | How do I run the pipeline / add a domain? |
| [legacy_src.md](legacy_src.md) | The retiring `src/` stack (reference only) |
