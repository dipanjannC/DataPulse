"""Column-level schema definitions for the sales dataset."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDefinition:
    """Describes a single column in the sales dataset."""

    name: str
    dtype: str
    description: str
    is_key: bool = False
    nullable: bool = False


ORDER_FIELDS: list[ColumnDefinition] = [
    ColumnDefinition(name="order_id", dtype="str", description="Unique order identifier", is_key=True),
    ColumnDefinition(name="customer_id", dtype="str", description="Reference to the purchasing customer"),
    ColumnDefinition(name="customer_name", dtype="str", description="Display name of the customer"),
    ColumnDefinition(name="product_id", dtype="str", description="Reference to the purchased product"),
    ColumnDefinition(name="product_name", dtype="str", description="Display name of the product"),
    ColumnDefinition(name="category", dtype="str", description="Product category"),
    ColumnDefinition(name="quantity", dtype="int", description="Number of units ordered"),
    ColumnDefinition(name="unit_price", dtype="float", description="Price per unit"),
    ColumnDefinition(name="order_date", dtype="date", description="Date the order was placed"),
    ColumnDefinition(name="region", dtype="str", description="Geographic sales region"),
    ColumnDefinition(name="channel", dtype="str", description="Sales channel (Online, Retail, Distributor)"),
]

EXPECTED_COLUMNS: list[str] = [f.name for f in ORDER_FIELDS]
