"""Knowledge graph schema definitions."""

from enum import Enum


class NodeType(Enum):
    CUSTOMER = "customer"
    ORDER = "order"
    PRODUCT = "product"
    REGION = "region"
    CHANNEL = "channel"
    CATEGORY = "category"


class EdgeType(Enum):
    PLACED = "placed"           # Customer -> Order
    CONTAINS = "contains"       # Order -> Product
    IN_REGION = "in_region"     # Order -> Region
    VIA_CHANNEL = "via_channel" # Order -> Channel
    BELONGS_TO = "belongs_to"   # Product -> Category
