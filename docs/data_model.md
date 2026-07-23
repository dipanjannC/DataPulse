# Data Model

The data model for the active `text2sql/` stack. The single source of truth is
`text2sql/metadata/schema.json` (v2.0); this doc is a human-readable projection of it. For the
legacy `src/` sales model see [legacy_src.md](legacy_src.md).

## The contract: `schema.json`

Read only through `text2sql/metadata/utils.py` — never parse the JSON directly elsewhere.

```jsonc
{
  "version": "2.0",
  "metrics": [ { "name", "expression", "tables", "description" } ],   // canonical measures
  "domains": [
    {
      "name": "Sales", "description": "...",
      "tables": [
        {
          "name": "orders", "description": "...",
          "columns": [
            { "name": "order_id", "type": "INTEGER", "description": "...",
              "primary_key": true, "nullable": false },
            { "name": "customer_id", "type": "INTEGER", "...": "...",
              "foreign_key": { "table": "customers", "column": "customer_id" } },
            { "name": "loyalty_tier", "type": "TEXT", "aliases": ["membership level", ...] }
          ]
        }
      ],
      "relationships": [
        { "from_table": "orders", "from_column": "customer_id",
          "to_table": "customers", "to_column": "customer_id" }
      ]
    }
  ]
}
```

Helpers (`utils.py`): `load_schema()`, `get_all_tables(schema)` (flat list, each with an added
`domain` key), `get_all_relationships(schema)` (flat list of all FK edges), `get_domains(schema)`,
`get_metrics(schema)`.

- **Column types:** `INTEGER`, `REAL`, `TEXT`, `DATE`, `DATETIME`.
- **`foreign_key`** on a column is mirrored by an entry in the domain's **`relationships`** list —
  `relationships` is the authoritative, complete FK source the loader/KG/validator use.
- **`aliases`** (optional) are natural-language synonyms embedded into the KG so retrieval matches
  colloquial phrasing (e.g. "membership level" → `loyalty_tier`).

## Domains and tables (5 × 10 = 50 tables)

| Domain | Tables |
|---|---|
| **Sales** | customers, products, categories, orders, order_items, regions, sales_reps, sales_targets, returns, invoices |
| **IT** | it_assets, it_incidents, it_projects, servers, software_licenses, change_requests, it_vendors, deployments, sla_definitions, it_tickets |
| **HR** | employees, departments, positions, payroll, leave_requests, performance_reviews, training_programs, employee_benefits, job_postings, attendance |
| **Marketing** | campaigns, leads, marketing_channels, content_assets, social_media_posts, email_campaigns, marketing_events, marketing_budgets, customer_segments, campaign_metrics |
| **Security** | sec_users, sec_roles, access_logs, sec_incidents, vulnerabilities, sec_policies, monitored_assets, sec_alerts, security_audits, compliance_controls |

## Referential integrity (40 FK edges)

All 40 FK relationships are declared **within** a single domain — the FK graph is five
self-contained subgraphs, so the domains are schema-isolated (no declared cross-domain joins).
Two edges are **self-referential**:

- `categories.parent_category_id → categories.category_id` (category hierarchy)
- `employees.manager_id → employees.employee_id` (reporting chain)

Nullable FKs are legitimate (e.g. `orders.rep_id`, `categories.parent_category_id`,
`departments.head_employee_id`) — a NULL means "no parent", not a broken reference. Nothing in the
SQLite DDL enforces these (no `REFERENCES` clause is emitted), so the [quality layer](quality.md)
is what actually checks them.

## Metric glossary (the semantic layer)

Canonical business measures live in `schema.json` and become `:Metric` nodes in the KG. They exist
to disambiguate *which column is "revenue"* — the agent is instructed to use these expressions
verbatim rather than guess a similar-looking column.

| Metric | Expression |
|---|---|
| total revenue | `SUM(order_items.line_total)` |
| average order value | `SUM(order_items.line_total) / COUNT(DISTINCT order_items.order_id)` |
| gross margin | `SUM((order_items.unit_price - products.cost_price) * order_items.quantity)` |
| target attainment rate | `SUM(sales_targets.achieved_amount) / SUM(sales_targets.target_amount)` |

## SQLite mapping (the execution store)

`db/loader.py` creates one table per schema table and bulk-loads its CSV. The type map:

| schema type | SQLite type |
|---|---|
| `INTEGER` | `INTEGER` |
| `REAL` | `REAL` |
| `TEXT` | `TEXT` |
| `DATE` | `TEXT` (ISO `YYYY-MM-DD`) |
| `DATETIME` | `TEXT` (ISO `YYYY-MM-DD HH:MM:SS`) |

DDL carries `PRIMARY KEY` and `NOT NULL` from the schema. `load()` returns a `LoadStats`
(rows per table). The DB file is `db/sales.db`, tracked in-repo.

## Neo4j mapping (the schema graph)

Built by `knowledge_graph/builder.py`. The graph holds **schema metadata, not row data** — the
agent searches it to *plan* a query.

**Nodes** (embeddings are 384-dim `all-MiniLM-L6-v2` vectors):

| Node | Key | Notable properties |
|---|---|---|
| `Domain` | `name` | `description`, `embedding` |
| `Table` | `name` | `description`, `domain`, `embedding` |
| `Column` | `key` (`table.column`) | `name`, `table_name`, `domain`, `description`, `data_type`, `is_primary_key`, `aliases`, `embedding` |
| `Metric` | `name` | `expression`, `description`, `tables` |

**Relationships:**

- `(Domain)-[:HAS_TABLE]->(Table)`
- `(Table)-[:HAS_COLUMN]->(Column)`
- `(Column)-[:FOREIGN_KEY]->(Column)` — column-level FK
- `(Table)-[:REFERENCES {from_column, to_column}]->(Table)` — table-level projection carrying the
  exact join keys, so the retriever can walk shortest join paths and hand the LLM explicit JOIN
  conditions

Vector indexes (`cosine`) exist on `Column`, `Table`, and `Domain` embeddings; UNIQUE constraints
on `Domain.name`, `Table.name`, `Column.key`, `Metric.name`. The build is idempotent (`MERGE`).

## Reading it in code

```python
from text2sql.metadata.utils import load_schema, get_all_tables, get_all_relationships

schema = load_schema()
for t in get_all_tables(schema):
    print(t["domain"], t["name"], [c["name"] for c in t["columns"]])
for r in get_all_relationships(schema):
    print(f'{r["from_table"]}.{r["from_column"]} -> {r["to_table"]}.{r["to_column"]}')
```
