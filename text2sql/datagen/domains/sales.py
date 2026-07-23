"""GENERATE — Sales domain: customers, products, orders, revenue, targets, returns."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

from text2sql.datagen.domains._common import rand_date


def generate_sales(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # regions (fixed)
    regions = pd.DataFrame([
        {"region_id": 1, "region_name": "North",   "country": "USA",    "manager_name": fake.name(), "timezone": "America/New_York"},
        {"region_id": 2, "region_name": "South",   "country": "USA",    "manager_name": fake.name(), "timezone": "America/Chicago"},
        {"region_id": 3, "region_name": "East",    "country": "USA",    "manager_name": fake.name(), "timezone": "America/New_York"},
        {"region_id": 4, "region_name": "West",    "country": "USA",    "manager_name": fake.name(), "timezone": "America/Los_Angeles"},
        {"region_id": 5, "region_name": "Central", "country": "Canada", "manager_name": fake.name(), "timezone": "America/Chicago"},
    ])
    tables["regions"] = regions
    region_ids = list(regions["region_id"])

    # categories (fixed)
    categories = pd.DataFrame([
        {"category_id": 1, "category_name": "Electronics",      "parent_category_id": None, "description": "Consumer electronics and gadgets"},
        {"category_id": 2, "category_name": "Clothing",         "parent_category_id": None, "description": "Apparel and fashion items"},
        {"category_id": 3, "category_name": "Home & Garden",    "parent_category_id": None, "description": "Home furnishings and garden supplies"},
        {"category_id": 4, "category_name": "Sports",           "parent_category_id": None, "description": "Sports and outdoor equipment"},
        {"category_id": 5, "category_name": "Books",            "parent_category_id": None, "description": "Books and digital media"},
        {"category_id": 6, "category_name": "Laptops",          "parent_category_id": 1,    "description": "Portable personal computers"},
        {"category_id": 7, "category_name": "Smartphones",      "parent_category_id": 1,    "description": "Mobile phones and accessories"},
        {"category_id": 8, "category_name": "Men's Clothing",   "parent_category_id": 2,    "description": "Men's apparel"},
        {"category_id": 9, "category_name": "Women's Clothing", "parent_category_id": 2,    "description": "Women's apparel"},
    ])
    tables["categories"] = categories
    cat_ids = list(categories["category_id"])

    # customers
    customers = pd.DataFrame([{
        "customer_id":  i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.email(),
        "phone":        fake.phone_number()[:15],
        "city":         fake.city(),
        "country":      rng.choice(["USA", "Canada", "UK"]),
        "signup_date":  rand_date(rng, date(2020, 1, 1), date(2023, 12, 31)),
        "loyalty_tier": rng.choice(["Bronze", "Silver", "Gold", "Platinum"]),
        "is_active":    rng.choices([1, 0], weights=[92, 8])[0],
    } for i in range(500)])
    tables["customers"] = customers
    cust_ids = list(customers["customer_id"])

    # products
    brands = ["TechPro", "StyleCo", "HomeBase", "SportMax", "ReadMore", "ApexTech", "FashionHub"]
    products = pd.DataFrame([{
        "product_id":     i + 1,
        "product_name":   f"{rng.choice(brands)} {fake.word().title()} {fake.bothify('##??').upper()}",
        "category_id":    rng.choice(cat_ids),
        "unit_price":     round(rng.uniform(5.0, 999.99), 2),
        "cost_price":     round(rng.uniform(2.0, 499.99), 2),
        "stock_quantity": rng.randint(0, 500),
        "brand":          rng.choice(brands),
        "is_active":      rng.choices([1, 0], weights=[90, 10])[0],
    } for i in range(200)])
    tables["products"] = products
    prod_prices = dict(zip(products["product_id"], products["unit_price"]))
    prod_ids = list(products["product_id"])

    # sales_reps
    sales_reps = pd.DataFrame([{
        "rep_id":       i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.company_email(),
        "region_id":    rng.choice(region_ids),
        "hire_date":    rand_date(rng, date(2018, 1, 1), date(2023, 6, 30)),
        "quota_amount": round(rng.uniform(200_000, 1_000_000), 2),
    } for i in range(30)])
    tables["sales_reps"] = sales_reps
    rep_ids = list(sales_reps["rep_id"])

    # orders
    orders = pd.DataFrame([{
        "order_id":      i + 1,
        "customer_id":   rng.choice(cust_ids),
        "rep_id":        rng.choice(rep_ids),
        "order_date":    rand_date(rng, date(2022, 1, 1), date(2024, 12, 31)),
        "status":        rng.choice(["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]),
        "channel":       rng.choice(["Online", "In-Store", "Phone"]),
        "discount_pct":  rng.choice([0, 0, 0, 5.0, 10.0, 15.0, 20.0]),
        "shipping_cost": round(rng.uniform(0.0, 25.0), 2),
        "region_id":     rng.choice(region_ids),
    } for i in range(2000)])
    tables["orders"] = orders
    order_ids = list(orders["order_id"])

    # order_items
    items, iid = [], 1
    for _, o in orders.iterrows():
        for _ in range(rng.randint(1, 4)):
            pid = rng.choice(prod_ids)
            qty = rng.randint(1, 5)
            price = prod_prices[pid]
            items.append({"item_id": iid, "order_id": int(o["order_id"]), "product_id": pid,
                          "quantity": qty, "unit_price": price, "line_total": round(price * qty, 2)})
            iid += 1
    tables["order_items"] = pd.DataFrame(items)

    # sales_targets
    targets = [{"target_id": i + 1, "rep_id": rep_ids[i // 4], "period_year": 2022 + (i % 4) // 4,
                "period_quarter": (i % 4) + 1,
                "target_amount": round(rng.uniform(50_000, 250_000), 2),
                "achieved_amount": round(rng.uniform(30_000, 270_000), 2)}
               for i in range(len(rep_ids) * 4)]
    tables["sales_targets"] = pd.DataFrame(targets)

    # returns
    return_order_sample = rng.sample(order_ids, min(200, len(order_ids)))
    returns = pd.DataFrame([{
        "return_id":     i + 1,
        "order_id":      return_order_sample[i],
        "product_id":    rng.choice(prod_ids),
        "return_date":   rand_date(rng, date(2022, 3, 1), date(2025, 1, 31)),
        "reason":        rng.choice(["Defective", "Wrong item", "Changed mind", "Not as described"]),
        "quantity":      rng.randint(1, 3),
        "refund_amount": round(rng.uniform(10.0, 500.0), 2),
    } for i in range(200)])
    tables["returns"] = returns

    # invoices (one per order)
    invoices = []
    for _, o in orders.iterrows():
        inv_date = date.fromisoformat(o["order_date"])
        due_date = inv_date + timedelta(days=30)
        invoices.append({
            "invoice_id":     int(o["order_id"]),
            "order_id":       int(o["order_id"]),
            "invoice_date":   str(inv_date),
            "due_date":       str(due_date),
            "amount":         round(rng.uniform(20.0, 2000.0), 2),
            "status":         rng.choice(["Paid", "Paid", "Paid", "Unpaid", "Overdue"]),
            "payment_method": rng.choice(["Credit Card", "Bank Transfer", "Cash"]),
        })
    tables["invoices"] = pd.DataFrame(invoices)

    return tables
