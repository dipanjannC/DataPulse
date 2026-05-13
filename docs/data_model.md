# Data Model

## Sales Entities

| Entity | Key Fields |
|---|---|
| **Order** | order_id, customer_id, product_id, quantity, unit_price, order_date, region, channel |
| **Product** | product_id, product_name, category |
| **Customer** | customer_id, customer_name |
| **Region** | name (e.g. North America, Europe, Asia Pacific) |
| **Channel** | name (e.g. Online, Retail, Distributor) |
| **Category** | name (e.g. Electronics, Stationery, Furniture) |

## Neo4j Mapping

Node labels and relationship types are the canonical Cypher strings — defined once in `src/graph/domain/schema.py` and reused by the builder, the agent's schema card, and the tests.

**Node labels:**

| Label | Unique key | Other properties |
|---|---|---|
| `Customer` | `customer_id` | `customer_name` |
| `Order` | `order_id` | `quantity`, `unit_price`, `order_date` |
| `Product` | `product_id` | `product_name` |
| `Region` | `name` | — |
| `Channel` | `name` | — |
| `Category` | `name` | — |

**Relationships:**

- `(Customer)-[:PLACED]->(Order)`
- `(Order)-[:CONTAINS]->(Product)`
- `(Order)-[:IN_REGION]->(Region)`
- `(Order)-[:VIA_CHANNEL]->(Channel)`
- `(Product)-[:BELONGS_TO]->(Category)`

Constraints (created on first load by `Neo4jStore.setup_constraints()`):

```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Order)    REQUIRE n.order_id    IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Product)  REQUIRE n.product_id  IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Region)   REQUIRE n.name        IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Channel)  REQUIRE n.name        IS UNIQUE
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Category) REQUIRE n.name        IS UNIQUE
```

The loader uses `MERGE` for both nodes and relationships, so re-running on the same CSV is idempotent.
