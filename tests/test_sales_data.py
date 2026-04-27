"""Tests for the sales_data bounded context."""

from datetime import date

from src.sales_data.domain.models import Customer, Order, Product


def test_product_creation():
    product = Product(product_id="PROD-001", product_name="Widget", category="Gadgets")
    assert product.product_id == "PROD-001"
    assert product.category == "Gadgets"


def test_customer_creation():
    customer = Customer(customer_id="CUST-001", customer_name="Jane Doe")
    assert customer.customer_name == "Jane Doe"


def test_order_creation():
    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        product_id="PROD-001",
        quantity=3,
        unit_price=19.99,
        order_date=date(2024, 1, 15),
        region="North America",
        channel="Online",
    )
    assert order.quantity == 3
    assert order.unit_price == 19.99
