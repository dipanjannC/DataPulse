"""Field-level metadata for sales data columns."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldMeta:
    """Describes a single column in the sales dataset."""

    name: str
    dtype: str
    description: str
    is_key: bool = False
    nullable: bool = False


ORDER_FIELDS: list[FieldMeta] = [
    FieldMeta(name="order_id", dtype="str", description="Unique order identifier", is_key=True),
    FieldMeta(name="customer_id", dtype="str", description="Reference to the purchasing customer"),
    FieldMeta(name="customer_name", dtype="str", description="Display name of the customer"),
    FieldMeta(name="product_id", dtype="str", description="Reference to the purchased product"),
    FieldMeta(name="product_name", dtype="str", description="Display name of the product"),
    FieldMeta(name="category", dtype="str", description="Product category"),
    FieldMeta(name="quantity", dtype="int", description="Number of units ordered"),
    FieldMeta(name="unit_price", dtype="float", description="Price per unit"),
    FieldMeta(name="order_date", dtype="date", description="Date the order was placed"),
    FieldMeta(name="region", dtype="str", description="Geographic sales region"),
    FieldMeta(name="channel", dtype="str", description="Sales channel (Online, Retail, Distributor)"),
]

EXPECTED_COLUMNS: list[str] = [f.name for f in ORDER_FIELDS]
