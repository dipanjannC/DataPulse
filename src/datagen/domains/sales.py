"""GENERATE — Sales domain: customers, products, orders, revenue, targets, returns."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date
from src.datagen.fixtures import load_fixture
from src.datagen.vocab import values_for


def generate_sales(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # regions — reference data in fixtures/regions.json; manager_name filled per row
    region_rows = load_fixture("regions")
    for row in region_rows:
        row["manager_name"] = fake.name()
    regions = pd.DataFrame(region_rows)
    tables["regions"] = regions
    region_ids = list(regions["region_id"])

    # categories — reference data in fixtures/categories.json
    categories = pd.DataFrame(load_fixture("categories"))
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
        "loyalty_tier": rng.choice(values_for("customers", "loyalty_tier")),
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
        "status":        rng.choice(values_for("orders", "status")),
        "channel":       rng.choice(values_for("orders", "channel")),
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
        "reason":        rng.choice(values_for("returns", "reason")),
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
            "payment_method": rng.choice(values_for("invoices", "payment_method")),
        })
    tables["invoices"] = pd.DataFrame(invoices)

    return tables
