# Data Model

## Sales Entities

| Entity | Key Fields |
|---|---|
| **Order** | order_id, customer_id, product_id, quantity, unit_price, order_date, region, channel |
| **Product** | product_id, product_name, category |
| **Customer** | customer_id, customer_name |
| **Region** | name (e.g. North America, Europe, Asia Pacific) |
| **Channel** | name (e.g. Online, Retail, Distributor) |

## Graph Mapping

Entities become **nodes**; relationships become **edges**:

- `Customer` --PLACED--> `Order`
- `Order` --CONTAINS--> `Product`
- `Order` --IN_REGION--> `Region`
- `Order` --VIA_CHANNEL--> `Channel`
- `Product` --BELONGS_TO--> `Category` (derived from product category field)

Node properties carry the full entity attributes. Edge properties may carry quantity and unit_price where relevant.
