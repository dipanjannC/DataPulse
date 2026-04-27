"""Sales domain models."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Product:
    product_id: str
    product_name: str
    category: str


@dataclass
class Customer:
    customer_id: str
    customer_name: str


@dataclass
class Order:
    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    unit_price: float
    order_date: date
    region: str
    channel: str
