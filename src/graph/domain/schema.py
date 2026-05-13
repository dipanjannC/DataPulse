"""Knowledge graph schema definitions.

Enum values are the canonical Cypher strings: CamelCase for node labels,
UPPER_SNAKE_CASE for relationship types. They are the source of truth for
the Neo4j builder and the agent's schema card.
"""

from enum import Enum


class NodeType(Enum):
    CUSTOMER = "Customer"
    ORDER = "Order"
    PRODUCT = "Product"
    REGION = "Region"
    CHANNEL = "Channel"
    CATEGORY = "Category"


class EdgeType(Enum):
    PLACED = "PLACED"            # Customer -> Order
    CONTAINS = "CONTAINS"        # Order -> Product
    IN_REGION = "IN_REGION"      # Order -> Region
    VIA_CHANNEL = "VIA_CHANNEL"  # Order -> Channel
    BELONGS_TO = "BELONGS_TO"    # Product -> Category
