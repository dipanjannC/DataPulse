# Query Engine

## Query Modes

### Simple (Graph Traversal)

`SimpleResolver` translates structured `Query` objects into NetworkX graph operations — neighbor lookups, path finding, and filtered traversals. No LLM required.

Example queries:
- "All orders placed by customer CUST-101"
- "Products sold in the Europe region"
- "Shortest path between two customers via shared products"

### Agentic (LLM-Driven)

`AgenticResolver` accepts natural-language questions, uses an LLM (via LangChain) to plan graph operations, executes them, and synthesizes a human-readable answer.

Example queries:
- "Which region had the highest revenue last quarter?"
- "Find customers who bought electronics and stationery"

## Query / Result Contract

```python
Query(query_type=..., parameters={...})  ->  QueryResult(data=..., metadata={...})
```

Both resolvers accept a `Query` and return a `QueryResult`, so callers can swap modes transparently.
