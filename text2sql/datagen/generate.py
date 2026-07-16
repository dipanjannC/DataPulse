"""Step 2 — Synthetic data generator.

Generates realistic CSV data for all 5 domains (Sales, IT, HR, Marketing, Security).
Output goes to text2sql/data/ — one CSV per table.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DATA_DIR = Path(__file__).parent.parent / "data"


# ── shared helpers ────────────────────────────────────────────────────────────

def _rand_date(start: date, end: date) -> str:
    return str(start + timedelta(days=random.randint(0, (end - start).days)))

def _rand_dt(start: date, end: date) -> str:
    d = start + timedelta(days=random.randint(0, (end - start).days))
    h, m = random.randint(0, 23), random.randint(0, 59)
    return f"{d} {h:02d}:{m:02d}:00"

def _save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(DATA_DIR / f"{name}.csv", index=False)
    print(f"  [{name:<30s}]  {len(df):>6,} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN 1 — SALES
# ═══════════════════════════════════════════════════════════════════════════════

def _sales() -> None:
    print("\n── Sales ──")

    # regions (fixed)
    regions = pd.DataFrame([
        {"region_id": 1, "region_name": "North",   "country": "USA",    "manager_name": fake.name(), "timezone": "America/New_York"},
        {"region_id": 2, "region_name": "South",   "country": "USA",    "manager_name": fake.name(), "timezone": "America/Chicago"},
        {"region_id": 3, "region_name": "East",    "country": "USA",    "manager_name": fake.name(), "timezone": "America/New_York"},
        {"region_id": 4, "region_name": "West",    "country": "USA",    "manager_name": fake.name(), "timezone": "America/Los_Angeles"},
        {"region_id": 5, "region_name": "Central", "country": "Canada", "manager_name": fake.name(), "timezone": "America/Chicago"},
    ])
    _save(regions, "regions")
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
    _save(categories, "categories")
    cat_ids = list(categories["category_id"])

    # customers
    customers = pd.DataFrame([{
        "customer_id":  i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.email(),
        "phone":        fake.phone_number()[:15],
        "city":         fake.city(),
        "country":      random.choice(["USA", "Canada", "UK"]),
        "signup_date":  _rand_date(date(2020, 1, 1), date(2023, 12, 31)),
        "loyalty_tier": random.choice(["Bronze", "Silver", "Gold", "Platinum"]),
        "is_active":    random.choices([1, 0], weights=[92, 8])[0],
    } for i in range(500)])
    _save(customers, "customers")
    cust_ids = list(customers["customer_id"])

    # products
    brands = ["TechPro", "StyleCo", "HomeBase", "SportMax", "ReadMore", "ApexTech", "FashionHub"]
    products = pd.DataFrame([{
        "product_id":     i + 1,
        "product_name":   f"{random.choice(brands)} {fake.word().title()} {fake.bothify('##??').upper()}",
        "category_id":    random.choice(cat_ids),
        "unit_price":     round(random.uniform(5.0, 999.99), 2),
        "cost_price":     round(random.uniform(2.0, 499.99), 2),
        "stock_quantity": random.randint(0, 500),
        "brand":          random.choice(brands),
        "is_active":      random.choices([1, 0], weights=[90, 10])[0],
    } for i in range(200)])
    _save(products, "products")
    prod_prices = dict(zip(products["product_id"], products["unit_price"]))
    prod_ids = list(products["product_id"])

    # sales_reps
    sales_reps = pd.DataFrame([{
        "rep_id":       i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.company_email(),
        "region_id":    random.choice(region_ids),
        "hire_date":    _rand_date(date(2018, 1, 1), date(2023, 6, 30)),
        "quota_amount": round(random.uniform(200_000, 1_000_000), 2),
    } for i in range(30)])
    _save(sales_reps, "sales_reps")
    rep_ids = list(sales_reps["rep_id"])

    # orders
    orders = pd.DataFrame([{
        "order_id":      i + 1,
        "customer_id":   random.choice(cust_ids),
        "rep_id":        random.choice(rep_ids),
        "order_date":    _rand_date(date(2022, 1, 1), date(2024, 12, 31)),
        "status":        random.choice(["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]),
        "channel":       random.choice(["Online", "In-Store", "Phone"]),
        "discount_pct":  random.choice([0, 0, 0, 5.0, 10.0, 15.0, 20.0]),
        "shipping_cost": round(random.uniform(0.0, 25.0), 2),
        "region_id":     random.choice(region_ids),
    } for i in range(2000)])
    _save(orders, "orders")
    order_ids = list(orders["order_id"])

    # order_items
    items, iid = [], 1
    for _, o in orders.iterrows():
        for _ in range(random.randint(1, 4)):
            pid = random.choice(prod_ids)
            qty = random.randint(1, 5)
            price = prod_prices[pid]
            items.append({"item_id": iid, "order_id": int(o["order_id"]), "product_id": pid,
                          "quantity": qty, "unit_price": price, "line_total": round(price * qty, 2)})
            iid += 1
    _save(pd.DataFrame(items), "order_items")

    # sales_targets
    targets = [{"target_id": i + 1, "rep_id": rep_ids[i // 4], "period_year": 2022 + (i % 4) // 4,
                "period_quarter": (i % 4) + 1,
                "target_amount": round(random.uniform(50_000, 250_000), 2),
                "achieved_amount": round(random.uniform(30_000, 270_000), 2)}
               for i in range(len(rep_ids) * 4)]
    _save(pd.DataFrame(targets), "sales_targets")

    # returns
    return_order_sample = random.sample(order_ids, min(200, len(order_ids)))
    returns = pd.DataFrame([{
        "return_id":     i + 1,
        "order_id":      return_order_sample[i],
        "product_id":    random.choice(prod_ids),
        "return_date":   _rand_date(date(2022, 3, 1), date(2025, 1, 31)),
        "reason":        random.choice(["Defective", "Wrong item", "Changed mind", "Not as described"]),
        "quantity":      random.randint(1, 3),
        "refund_amount": round(random.uniform(10.0, 500.0), 2),
    } for i in range(200)])
    _save(returns, "returns")

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
            "amount":         round(random.uniform(20.0, 2000.0), 2),
            "status":         random.choice(["Paid", "Paid", "Paid", "Unpaid", "Overdue"]),
            "payment_method": random.choice(["Credit Card", "Bank Transfer", "Cash"]),
        })
    _save(pd.DataFrame(invoices), "invoices")


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN 2 — IT
# ═══════════════════════════════════════════════════════════════════════════════

def _it() -> None:
    print("\n── IT ──")

    # it_vendors
    service_types = ["Hardware", "Software", "Cloud", "Networking", "Managed Services"]
    vendors = pd.DataFrame([{
        "vendor_id":      i + 1,
        "vendor_name":    fake.company(),
        "contact_email":  fake.company_email(),
        "service_type":   random.choice(service_types),
        "contract_start": _rand_date(date(2020, 1, 1), date(2023, 6, 30)),
        "contract_end":   _rand_date(date(2024, 1, 1), date(2026, 12, 31)),
        "annual_spend":   round(random.uniform(5_000, 500_000), 2),
    } for i in range(20)])
    _save(vendors, "it_vendors")

    # it_projects
    statuses = ["Planning", "Active", "On Hold", "Completed", "Cancelled"]
    projects = pd.DataFrame([{
        "project_id":      i + 1,
        "project_name":    f"{fake.bs().title()} System",
        "description":     fake.sentence(),
        "start_date":      _rand_date(date(2022, 1, 1), date(2024, 1, 1)),
        "end_date":        _rand_date(date(2024, 1, 1), date(2025, 12, 31)),
        "status":          random.choice(statuses),
        "budget":          round(random.uniform(10_000, 500_000), 2),
        "project_manager": fake.name(),
    } for i in range(30)])
    _save(projects, "it_projects")
    proj_ids = list(projects["project_id"])

    # sla_definitions (fixed)
    slas = pd.DataFrame([
        {"sla_id": 1, "service_name": "Email",         "priority": "Low",      "response_time_hours": 24, "resolution_time_hours": 72, "uptime_pct_target": 99.0},
        {"sla_id": 2, "service_name": "Email",         "priority": "Medium",   "response_time_hours": 8,  "resolution_time_hours": 24, "uptime_pct_target": 99.0},
        {"sla_id": 3, "service_name": "Email",         "priority": "High",     "response_time_hours": 4,  "resolution_time_hours": 8,  "uptime_pct_target": 99.0},
        {"sla_id": 4, "service_name": "Email",         "priority": "Critical", "response_time_hours": 1,  "resolution_time_hours": 4,  "uptime_pct_target": 99.0},
        {"sla_id": 5, "service_name": "Core Network",  "priority": "High",     "response_time_hours": 2,  "resolution_time_hours": 6,  "uptime_pct_target": 99.9},
        {"sla_id": 6, "service_name": "Core Network",  "priority": "Critical", "response_time_hours": 0.5,"resolution_time_hours": 2,  "uptime_pct_target": 99.9},
        {"sla_id": 7, "service_name": "ERP System",    "priority": "High",     "response_time_hours": 4,  "resolution_time_hours": 12, "uptime_pct_target": 99.5},
        {"sla_id": 8, "service_name": "ERP System",    "priority": "Critical", "response_time_hours": 1,  "resolution_time_hours": 4,  "uptime_pct_target": 99.5},
        {"sla_id": 9, "service_name": "Helpdesk",      "priority": "Low",      "response_time_hours": 48, "resolution_time_hours": 120,"uptime_pct_target": 98.0},
        {"sla_id": 10,"service_name": "Helpdesk",      "priority": "Medium",   "response_time_hours": 12, "resolution_time_hours": 48, "uptime_pct_target": 98.0},
        {"sla_id": 11,"service_name": "Cloud Storage", "priority": "High",     "response_time_hours": 2,  "resolution_time_hours": 8,  "uptime_pct_target": 99.99},
        {"sla_id": 12,"service_name": "Cloud Storage", "priority": "Critical", "response_time_hours": 0.5,"resolution_time_hours": 2,  "uptime_pct_target": 99.99},
    ])
    _save(slas, "sla_definitions")

    # servers
    envs = ["Production", "Staging", "Development", "DR"]
    oses = ["Ubuntu 22.04", "Ubuntu 20.04", "Windows Server 2022", "RHEL 9", "CentOS 8"]
    servers = pd.DataFrame([{
        "server_id":   i + 1,
        "hostname":    f"srv-{fake.bothify('??##').lower()}",
        "ip_address":  fake.ipv4_private(),
        "os":          random.choice(oses),
        "cpu_cores":   random.choice([4, 8, 16, 32, 64]),
        "ram_gb":      random.choice([8, 16, 32, 64, 128]),
        "storage_gb":  random.choice([256, 512, 1024, 2048, 4096]),
        "environment": random.choice(envs),
        "status":      random.choices(["Running", "Stopped", "Maintenance", "Decommissioned"], weights=[80, 8, 8, 4])[0],
    } for i in range(50)])
    _save(servers, "servers")

    # it_assets
    asset_types = ["Laptop", "Desktop", "Server", "Network Device", "Software"]
    assets = pd.DataFrame([{
        "asset_id":      i + 1,
        "asset_name":    f"{random.choice(['Dell', 'HP', 'Lenovo', 'Cisco', 'Apple'])} {fake.word().title()}",
        "asset_type":    random.choice(asset_types),
        "serial_number": fake.bothify("??###-??###-??###"),
        "purchase_date": _rand_date(date(2019, 1, 1), date(2024, 1, 1)),
        "purchase_cost": round(random.uniform(200.0, 5000.0), 2),
        "assigned_to":   fake.user_name(),
        "location":      random.choice(["HQ Floor 1", "HQ Floor 2", "Data Center", "Remote", "In Storage"]),
        "status":        random.choices(["Active", "In Repair", "Retired", "In Storage"], weights=[75, 10, 10, 5])[0],
    } for i in range(200)])
    _save(assets, "it_assets")

    # software_licenses
    sw_names = ["Microsoft Office", "Adobe Creative Cloud", "Slack", "Zoom", "Jira", "Confluence", "GitHub Enterprise", "Tableau", "Salesforce", "ServiceNow"]
    licenses = pd.DataFrame([{
        "license_id":    i + 1,
        "software_name": sw_names[i % len(sw_names)],
        "vendor":        random.choice(["Microsoft", "Adobe", "Atlassian", "Salesforce", "GitHub"]),
        "license_type":  random.choice(["Subscription", "Per Seat", "Site License", "Perpetual"]),
        "quantity":      random.choice([10, 25, 50, 100, 250, 500]),
        "expiry_date":   _rand_date(date(2024, 6, 1), date(2027, 12, 31)),
        "cost":          round(random.uniform(1_000, 100_000), 2),
        "assigned_to":   random.choice(["Engineering", "Marketing", "Finance", "HR", "All Staff"]),
    } for i in range(50)])
    _save(licenses, "software_licenses")

    # it_incidents
    categories_it = ["Network", "Hardware", "Software", "Security", "Access"]
    it_incidents = pd.DataFrame([{
        "incident_id": i + 1,
        "title":       fake.sentence(nb_words=6).rstrip("."),
        "severity":    random.choices(["Critical", "High", "Medium", "Low"], weights=[5, 15, 40, 40])[0],
        "category":    random.choice(categories_it),
        "status":      random.choices(["Open", "In Progress", "Resolved", "Closed"], weights=[10, 20, 30, 40])[0],
        "reported_by": fake.user_name(),
        "assigned_to": fake.user_name(),
        "created_at":  _rand_dt(date(2023, 1, 1), date(2025, 1, 1)),
        "resolved_at": None if random.random() < 0.15 else _rand_dt(date(2023, 1, 2), date(2025, 2, 1)),
    } for i in range(300)])
    _save(it_incidents, "it_incidents")
    inc_ids = list(it_incidents["incident_id"])

    # change_requests
    change_requests = pd.DataFrame([{
        "cr_id":        i + 1,
        "title":        f"Update {fake.word().title()} {random.choice(['Configuration', 'Firmware', 'Policy', 'Access'])}",
        "change_type":  random.choice(["Standard", "Emergency", "Normal"]),
        "priority":     random.choice(["Low", "Medium", "High", "Critical"]),
        "status":       random.choice(["Draft", "Pending Approval", "Approved", "Implemented", "Rejected"]),
        "requested_by": fake.user_name(),
        "approved_by":  fake.user_name() if random.random() > 0.2 else None,
        "planned_date": _rand_date(date(2024, 1, 1), date(2025, 12, 31)),
    } for i in range(100)])
    _save(change_requests, "change_requests")

    # deployments
    deployments = pd.DataFrame([{
        "deployment_id": i + 1,
        "project_id":    random.choice(proj_ids),
        "environment":   random.choice(["Development", "Staging", "Production"]),
        "version":       f"v{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,20)}",
        "deployed_at":   _rand_dt(date(2023, 1, 1), date(2025, 1, 1)),
        "deployed_by":   fake.user_name(),
        "status":        random.choices(["Success", "Failed", "Rolled Back"], weights=[80, 12, 8])[0],
    } for i in range(100)])
    _save(deployments, "deployments")

    # it_tickets
    teams = ["Network", "Desktop Support", "Security", "Cloud Ops", "Database"]
    tickets = pd.DataFrame([{
        "ticket_id":     i + 1,
        "incident_id":   random.choice(inc_ids) if random.random() < 0.3 else None,
        "ticket_type":   random.choice(["Incident", "Service Request", "Problem"]),
        "raised_by":     fake.user_name(),
        "assigned_team": random.choice(teams),
        "priority":      random.choice(["Low", "Medium", "High", "Critical"]),
        "status":        random.choices(["Open", "In Progress", "Pending", "Resolved", "Closed"], weights=[10, 20, 10, 25, 35])[0],
        "created_at":    _rand_dt(date(2023, 1, 1), date(2025, 1, 1)),
        "closed_at":     None if random.random() < 0.2 else _rand_dt(date(2023, 1, 2), date(2025, 2, 1)),
    } for i in range(500)])
    _save(tickets, "it_tickets")


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN 3 — HR
# ═══════════════════════════════════════════════════════════════════════════════

def _hr() -> None:
    print("\n── HR ──")

    # departments (fixed)
    dept_names = ["Engineering", "Finance", "Human Resources", "Marketing", "Sales",
                  "Operations", "Legal", "Product", "Customer Success", "Data & Analytics"]
    departments = pd.DataFrame([{
        "department_id":    i + 1,
        "department_name":  dept_names[i],
        "location":         random.choice(["New York", "San Francisco", "Chicago", "Austin", "Remote"]),
        "budget":           round(random.uniform(200_000, 5_000_000), 2),
        "head_employee_id": None,  # updated after employees are generated
    } for i in range(len(dept_names))])
    _save(departments, "departments")
    dept_ids = list(departments["department_id"])

    # positions
    levels = ["Junior", "Mid", "Senior", "Lead", "Director"]
    position_titles = [
        "Software Engineer", "Data Analyst", "HR Manager", "Marketing Specialist", "Sales Executive",
        "DevOps Engineer", "Product Manager", "Financial Analyst", "Legal Counsel", "UX Designer",
        "Data Scientist", "Business Analyst", "Operations Manager", "Customer Success Manager",
        "Security Engineer", "Cloud Architect", "Recruiter", "Payroll Specialist", "QA Engineer",
        "Technical Writer", "Project Manager", "Account Manager", "Content Strategist",
        "Network Engineer", "Database Administrator", "Scrum Master", "BI Developer",
        "Compliance Officer", "IT Support Specialist", "Solutions Architect"
    ]
    positions = pd.DataFrame([{
        "position_id":   i + 1,
        "title":         position_titles[i],
        "department_id": random.choice(dept_ids),
        "level":         random.choice(levels),
        "min_salary":    round(random.uniform(40_000, 100_000), 2),
        "max_salary":    round(random.uniform(100_001, 250_000), 2),
    } for i in range(len(position_titles))])
    _save(positions, "positions")
    pos_ids = list(positions["position_id"])

    # employees
    emp_types = ["Full-Time", "Part-Time", "Contractor", "Intern"]
    employees = pd.DataFrame([{
        "employee_id":     i + 1,
        "first_name":      fake.first_name(),
        "last_name":       fake.last_name(),
        "email":           fake.unique.company_email(),
        "department_id":   random.choice(dept_ids),
        "position_id":     random.choice(pos_ids),
        "hire_date":       _rand_date(date(2015, 1, 1), date(2024, 6, 30)),
        "employment_type": random.choices(emp_types, weights=[70, 10, 15, 5])[0],
        "manager_id":      None,  # set below
    } for i in range(300)])
    emp_ids = list(employees["employee_id"])
    # assign managers (each employee has a random senior employee as manager, top 10% are managers)
    manager_pool = emp_ids[:30]
    employees["manager_id"] = [None if i < 10 else random.choice(manager_pool) for i in range(len(employees))]
    _save(employees, "employees")

    # payroll (last 12 months per employee — sample 300 × 6 periods)
    payroll_rows = []
    for eid in random.sample(emp_ids, min(300, len(emp_ids))):
        for m in range(1, 7):
            gross = round(random.uniform(3_000, 18_000), 2)
            ded   = round(gross * random.uniform(0.20, 0.35), 2)
            payroll_rows.append({
                "payroll_id":   len(payroll_rows) + 1,
                "employee_id":  eid,
                "pay_period":   f"2024-{m:02d}",
                "gross_salary": gross,
                "deductions":   ded,
                "net_salary":   round(gross - ded, 2),
                "payment_date": str(date(2024, m, 28)),
            })
    _save(pd.DataFrame(payroll_rows), "payroll")

    # leave_requests
    leave_types = ["Annual", "Sick", "Maternity", "Paternity", "Unpaid"]
    leave_rows = []
    for i in range(500):
        sd  = date.fromisoformat(_rand_date(date(2023, 1, 1), date(2024, 12, 31)))
        days = random.randint(1, 15)
        ed  = sd + timedelta(days=days)
        leave_rows.append({
            "leave_id":    i + 1,
            "employee_id": random.choice(emp_ids),
            "leave_type":  random.choice(leave_types),
            "start_date":  str(sd),
            "end_date":    str(ed),
            "days_count":  days,
            "status":      random.choices(["Approved", "Approved", "Pending", "Rejected"], weights=[60, 20, 15, 5])[0],
            "approved_by": random.choice(manager_pool),
        })
    _save(pd.DataFrame(leave_rows), "leave_requests")

    # performance_reviews
    reviews = pd.DataFrame([{
        "review_id":     i + 1,
        "employee_id":   random.choice(emp_ids),
        "reviewer_id":   random.choice(manager_pool),
        "review_period": random.choice(["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2023", "Annual 2023"]),
        "rating":        round(random.uniform(1.5, 5.0), 1),
        "comments":      fake.sentence(),
        "review_date":   _rand_date(date(2023, 10, 1), date(2025, 1, 31)),
    } for i in range(300)])
    _save(reviews, "performance_reviews")

    # training_programs
    programs = ["Python for Data Science", "Leadership Essentials", "AWS Cloud Practitioner",
                "Agile & Scrum Fundamentals", "Excel Advanced", "Cybersecurity Awareness",
                "Communication Skills", "Project Management Professional", "SQL Bootcamp", "Design Thinking"]
    training = pd.DataFrame([{
        "training_id":     i + 1,
        "employee_id":     random.choice(emp_ids),
        "program_name":    random.choice(programs),
        "provider":        random.choice(["Coursera", "Udemy", "LinkedIn Learning", "Internal", "Pluralsight"]),
        "start_date":      _rand_date(date(2023, 1, 1), date(2024, 6, 30)),
        "completion_date": None if random.random() < 0.2 else _rand_date(date(2023, 2, 1), date(2025, 1, 1)),
        "status":          random.choices(["Completed", "In Progress", "Enrolled", "Dropped"], weights=[60, 20, 12, 8])[0],
        "cost":            round(random.uniform(50.0, 3_000.0), 2),
    } for i in range(400)])
    _save(training, "training_programs")

    # employee_benefits
    benefit_types = ["Health", "Dental", "Vision", "Retirement", "Life Insurance"]
    benefits = pd.DataFrame([{
        "benefit_id":            i + 1,
        "employee_id":           random.choice(emp_ids),
        "benefit_type":          random.choice(benefit_types),
        "plan_name":             random.choice(["Blue Cross PPO", "Aetna HMO", "Fidelity 401k", "MetLife Vision", "Prudential Life"]),
        "enrollment_date":       _rand_date(date(2018, 1, 1), date(2024, 6, 30)),
        "employer_contribution": round(random.uniform(100.0, 600.0), 2),
        "employee_contribution": round(random.uniform(0.0, 300.0), 2),
    } for i in range(600)])
    _save(benefits, "employee_benefits")

    # job_postings
    postings = pd.DataFrame([{
        "posting_id":      i + 1,
        "position_id":     random.choice(pos_ids),
        "department_id":   random.choice(dept_ids),
        "posted_date":     _rand_date(date(2023, 1, 1), date(2024, 12, 31)),
        "closing_date":    _rand_date(date(2024, 1, 1), date(2025, 6, 30)),
        "status":          random.choices(["Open", "Closed", "On Hold", "Filled"], weights=[30, 25, 10, 35])[0],
        "applicant_count": random.randint(5, 200),
    } for i in range(50)])
    _save(postings, "job_postings")

    # attendance (sample — 300 employees × 10 days)
    att_rows = []
    for i, eid in enumerate(random.sample(emp_ids, min(300, len(emp_ids)))):
        for day_offset in range(10):
            d = date(2024, 6, 1) + timedelta(days=day_offset)
            if d.weekday() >= 5:
                continue
            status = random.choices(["Present", "Absent", "Half Day", "On Leave"], weights=[80, 5, 10, 5])[0]
            check_in  = f"{random.randint(8, 10):02d}:{random.randint(0, 59):02d}" if status in ("Present", "Half Day") else None
            check_out = f"{random.randint(16, 19):02d}:{random.randint(0, 59):02d}" if status == "Present" else None
            att_rows.append({
                "attendance_id": len(att_rows) + 1,
                "employee_id":   eid,
                "date":          str(d),
                "check_in":      check_in,
                "check_out":     check_out,
                "hours_worked":  round(random.uniform(4, 9), 1) if status == "Present" else None,
                "status":        status,
            })
    _save(pd.DataFrame(att_rows), "attendance")


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN 4 — MARKETING
# ═══════════════════════════════════════════════════════════════════════════════

def _marketing() -> None:
    print("\n── Marketing ──")

    # marketing_channels (fixed)
    channels = pd.DataFrame([
        {"channel_id": 1, "channel_name": "Google Ads",   "channel_type": "Paid",    "cost_per_click": 1.85, "cost_per_impression": 3.50,  "monthly_budget": 20000},
        {"channel_id": 2, "channel_name": "Facebook Ads", "channel_type": "Paid",    "cost_per_click": 0.95, "cost_per_impression": 1.20,  "monthly_budget": 15000},
        {"channel_id": 3, "channel_name": "LinkedIn",     "channel_type": "Social",  "cost_per_click": 5.50, "cost_per_impression": 8.00,  "monthly_budget": 10000},
        {"channel_id": 4, "channel_name": "Email",        "channel_type": "Email",   "cost_per_click": 0.10, "cost_per_impression": None,   "monthly_budget": 2000},
        {"channel_id": 5, "channel_name": "SEO / Organic","channel_type": "Organic", "cost_per_click": None, "cost_per_impression": None,   "monthly_budget": 5000},
        {"channel_id": 6, "channel_name": "Instagram",    "channel_type": "Social",  "cost_per_click": 1.20, "cost_per_impression": 2.00,  "monthly_budget": 8000},
        {"channel_id": 7, "channel_name": "Twitter/X",    "channel_type": "Social",  "cost_per_click": 0.60, "cost_per_impression": 0.90,  "monthly_budget": 5000},
        {"channel_id": 8, "channel_name": "Events",       "channel_type": "Events",  "cost_per_click": None, "cost_per_impression": None,   "monthly_budget": 30000},
    ])
    _save(channels, "marketing_channels")
    chan_ids = list(channels["channel_id"])

    # campaigns
    camp_types = ["Brand Awareness", "Lead Generation", "Product Launch", "Retention"]
    campaigns = pd.DataFrame([{
        "campaign_id":   i + 1,
        "campaign_name": f"{fake.catch_phrase()} Campaign",
        "campaign_type": random.choice(camp_types),
        "channel_id":    random.choice(chan_ids),
        "start_date":    _rand_date(date(2022, 1, 1), date(2024, 6, 30)),
        "end_date":      _rand_date(date(2024, 7, 1), date(2025, 6, 30)),
        "budget":        round(random.uniform(5_000, 200_000), 2),
        "status":        random.choices(["Draft", "Active", "Paused", "Completed"], weights=[10, 40, 15, 35])[0],
        "owner":         fake.name(),
    } for i in range(50)])
    _save(campaigns, "campaigns")
    camp_ids = list(campaigns["campaign_id"])

    # leads
    sources = ["Organic Search", "Paid Ad", "Social Media", "Referral", "Event"]
    leads = pd.DataFrame([{
        "lead_id":      i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.email(),
        "source":       random.choice(sources),
        "campaign_id":  random.choice(camp_ids),
        "status":       random.choices(["New", "Contacted", "Qualified", "Converted", "Lost"], weights=[20, 25, 20, 20, 15])[0],
        "created_at":   _rand_date(date(2022, 1, 1), date(2025, 1, 31)),
        "converted_at": None if random.random() < 0.7 else _rand_date(date(2022, 2, 1), date(2025, 3, 1)),
    } for i in range(1000)])
    _save(leads, "leads")

    # content_assets
    asset_types = ["Blog Post", "Video", "Infographic", "Landing Page", "Whitepaper"]
    content = pd.DataFrame([{
        "asset_id":     i + 1,
        "title":        fake.sentence(nb_words=5).rstrip("."),
        "asset_type":   random.choice(asset_types),
        "campaign_id":  random.choice(camp_ids),
        "created_by":   fake.name(),
        "publish_date": _rand_date(date(2022, 1, 1), date(2025, 1, 31)),
        "status":       random.choices(["Draft", "In Review", "Published", "Archived"], weights=[10, 15, 60, 15])[0],
    } for i in range(200)])
    _save(content, "content_assets")

    # social_media_posts
    platforms = ["LinkedIn", "Twitter", "Facebook", "Instagram"]
    posts = pd.DataFrame([{
        "post_id":      i + 1,
        "platform":     random.choice(platforms),
        "content_text": fake.sentence(),
        "campaign_id":  random.choice(camp_ids),
        "published_at": _rand_dt(date(2022, 1, 1), date(2025, 1, 31)),
        "likes":        random.randint(0, 5000),
        "shares":       random.randint(0, 500),
        "reach":        random.randint(100, 100_000),
    } for i in range(300)])
    _save(posts, "social_media_posts")

    # email_campaigns
    emails = pd.DataFrame([{
        "email_id":      i + 1,
        "campaign_id":   random.choice(camp_ids),
        "subject":       fake.sentence(nb_words=6).rstrip("."),
        "sent_to_count": random.randint(500, 50_000),
        "open_count":    random.randint(50, 15_000),
        "click_count":   random.randint(10, 5_000),
        "bounce_count":  random.randint(0, 500),
        "sent_at":       _rand_dt(date(2022, 1, 1), date(2025, 1, 31)),
    } for i in range(100)])
    _save(emails, "email_campaigns")

    # marketing_events
    event_types = ["Webinar", "Trade Show", "Conference", "Workshop", "Product Demo"]
    events = pd.DataFrame([{
        "event_id":       i + 1,
        "event_name":     f"{fake.company()} {random.choice(['Summit', 'Forum', 'Expo', 'Workshop'])} {2023 + i % 2}",
        "event_type":     random.choice(event_types),
        "campaign_id":    random.choice(camp_ids),
        "start_date":     _rand_date(date(2022, 1, 1), date(2025, 1, 31)),
        "end_date":       _rand_date(date(2025, 2, 1), date(2025, 12, 31)),
        "budget":         round(random.uniform(2_000, 100_000), 2),
        "attendee_count": random.randint(10, 5_000),
    } for i in range(30)])
    _save(events, "marketing_events")

    # marketing_budgets
    budgets = pd.DataFrame([{
        "budget_id":        i + 1,
        "campaign_id":      camp_ids[i % len(camp_ids)],
        "period_year":      random.choice([2022, 2023, 2024]),
        "period_quarter":   random.randint(1, 4),
        "allocated_amount": round(random.uniform(5_000, 80_000), 2),
        "spent_amount":     round(random.uniform(1_000, 80_000), 2),
    } for i in range(200)])
    _save(budgets, "marketing_budgets")

    # customer_segments
    segments = pd.DataFrame([
        {"segment_id": 1,  "segment_name": "High-Value Customers",   "criteria": "Total spend > $5000",          "customer_count": random.randint(200, 2000),  "created_at": "2023-01-01", "last_updated": "2024-06-01"},
        {"segment_id": 2,  "segment_name": "New Signups",            "criteria": "Signup within last 30 days",   "customer_count": random.randint(50, 500),   "created_at": "2023-01-01", "last_updated": "2024-12-01"},
        {"segment_id": 3,  "segment_name": "Churned Users",          "criteria": "No purchase in 180 days",      "customer_count": random.randint(100, 1000), "created_at": "2023-03-01", "last_updated": "2024-11-01"},
        {"segment_id": 4,  "segment_name": "Gold Tier Customers",    "criteria": "loyalty_tier = Gold",          "customer_count": random.randint(300, 1500), "created_at": "2023-01-01", "last_updated": "2024-10-01"},
        {"segment_id": 5,  "segment_name": "Enterprise Accounts",    "criteria": "Company size > 500 employees", "customer_count": random.randint(50, 300),   "created_at": "2023-06-01", "last_updated": "2024-09-01"},
        {"segment_id": 6,  "segment_name": "Webinar Attendees",      "criteria": "Attended any webinar event",   "customer_count": random.randint(100, 800),  "created_at": "2023-07-01", "last_updated": "2024-08-01"},
        {"segment_id": 7,  "segment_name": "Email Clickers",         "criteria": "Clicked email link in 60 days","customer_count": random.randint(200, 2000), "created_at": "2023-02-01", "last_updated": "2024-12-15"},
        {"segment_id": 8,  "segment_name": "Mobile Users",           "criteria": "Primary device = Mobile",      "customer_count": random.randint(500, 5000), "created_at": "2023-04-01", "last_updated": "2024-11-30"},
        {"segment_id": 9,  "segment_name": "Discount Seekers",       "criteria": "Purchased with discount > 15%","customer_count": random.randint(100, 800),  "created_at": "2023-05-01", "last_updated": "2024-10-15"},
        {"segment_id": 10, "segment_name": "Repeat Buyers",          "criteria": "Order count >= 5",             "customer_count": random.randint(150, 1200), "created_at": "2023-01-01", "last_updated": "2024-12-01"},
    ])
    _save(segments, "customer_segments")

    # campaign_metrics (daily metrics per campaign — 1000 records)
    metrics = pd.DataFrame([{
        "metric_id":          i + 1,
        "campaign_id":        random.choice(camp_ids),
        "metric_date":        _rand_date(date(2022, 1, 1), date(2025, 1, 31)),
        "impressions":        random.randint(1_000, 500_000),
        "clicks":             random.randint(10, 20_000),
        "conversions":        random.randint(0, 1_000),
        "revenue_attributed": round(random.uniform(0, 50_000), 2),
        "ctr":                round(random.uniform(0.001, 0.15), 4),
    } for i in range(1000)])
    _save(metrics, "campaign_metrics")


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN 5 — SECURITY
# ═══════════════════════════════════════════════════════════════════════════════

def _security() -> None:
    print("\n── Security ──")

    # sec_roles (fixed)
    roles = pd.DataFrame([
        {"role_id": 1, "role_name": "Admin",       "description": "Full system access",              "permission_level": 5, "created_at": "2020-01-01"},
        {"role_id": 2, "role_name": "Power User",  "description": "Elevated read/write access",      "permission_level": 4, "created_at": "2020-01-01"},
        {"role_id": 3, "role_name": "Standard",    "description": "Standard read/write access",      "permission_level": 3, "created_at": "2020-01-01"},
        {"role_id": 4, "role_name": "Read-Only",   "description": "View-only access to most systems","permission_level": 2, "created_at": "2020-01-01"},
        {"role_id": 5, "role_name": "Auditor",     "description": "Audit and compliance access",     "permission_level": 2, "created_at": "2020-01-01"},
        {"role_id": 6, "role_name": "Guest",       "description": "Minimal temporary access",        "permission_level": 1, "created_at": "2020-01-01"},
    ])
    _save(roles, "sec_roles")
    role_ids = list(roles["role_id"])

    # sec_policies
    categories_sec = ["Access Control", "Data Protection", "Incident Response", "Compliance"]
    policies = pd.DataFrame([{
        "policy_id":      i + 1,
        "policy_name":    random.choice(["Acceptable Use Policy", "Password Policy", "Data Retention Policy",
                                         "Remote Access Policy", "Encryption Policy", "BYOD Policy",
                                         "Incident Response Plan", "Vulnerability Management Policy",
                                         "Access Control Policy", "Cloud Security Policy"]),
        "category":       random.choice(categories_sec),
        "effective_date": _rand_date(date(2020, 1, 1), date(2023, 12, 31)),
        "review_date":    _rand_date(date(2024, 1, 1), date(2026, 12, 31)),
        "owner":          random.choice(["CISO", "IT Security", "Legal", "Compliance Team"]),
        "status":         random.choices(["Active", "Under Review", "Retired"], weights=[75, 20, 5])[0],
    } for i in range(20)])
    _save(policies, "sec_policies")

    # monitored_assets
    asset_types = ["Server", "Endpoint", "Network Device", "Cloud Resource", "Application"]
    monitored = pd.DataFrame([{
        "asset_id":       i + 1,
        "asset_name":     f"{random.choice(['srv', 'app', 'db', 'fw', 'vpc'])}-{fake.bothify('??##')}",
        "asset_type":     random.choice(asset_types),
        "ip_address":     fake.ipv4_private(),
        "criticality":    random.choices(["Critical", "High", "Medium", "Low"], weights=[10, 25, 40, 25])[0],
        "owner":          random.choice(["Engineering", "IT Ops", "Security", "DevOps"]),
        "last_scan_date": _rand_date(date(2024, 1, 1), date(2025, 1, 31)),
        "risk_level":     random.choice(["High", "Medium", "Low"]),
    } for i in range(100)])
    _save(monitored, "monitored_assets")
    asset_ids = list(monitored["asset_id"])

    # sec_users
    depts = ["Engineering", "Finance", "HR", "Marketing", "Sales", "Legal", "Operations"]
    sec_users = pd.DataFrame([{
        "user_id":     i + 1,
        "username":    fake.unique.user_name(),
        "email":       fake.unique.company_email(),
        "department":  random.choice(depts),
        "role_id":     random.choices(role_ids, weights=[2, 5, 50, 25, 8, 10])[0],
        "created_at":  _rand_date(date(2018, 1, 1), date(2024, 6, 30)),
        "last_login":  _rand_dt(date(2024, 1, 1), date(2025, 1, 31)),
        "is_active":   random.choices([1, 0], weights=[90, 10])[0],
        "mfa_enabled": random.choices([1, 0], weights=[70, 30])[0],
    } for i in range(200)])
    _save(sec_users, "sec_users")
    user_ids = list(sec_users["user_id"])

    # access_logs
    resources = ["/admin/users", "/finance/reports", "/hr/payroll", "/api/data", "/dashboard",
                 "finance-db", "hr-db", "email-server", "/settings", "/audit-logs"]
    actions = ["Login", "Logout", "Read", "Write", "Delete", "Export"]
    logs = pd.DataFrame([{
        "log_id":      i + 1,
        "user_id":     random.choice(user_ids),
        "resource":    random.choice(resources),
        "action":      random.choice(actions),
        "ip_address":  fake.ipv4(),
        "timestamp":   _rand_dt(date(2024, 1, 1), date(2025, 1, 31)),
        "status":      random.choices(["Success", "Failure"], weights=[90, 10])[0],
        "device_type": random.choice(["Desktop", "Mobile", "Server"]),
    } for i in range(2000)])
    _save(logs, "access_logs")

    # vulnerabilities
    severities = ["Critical", "High", "Medium", "Low"]
    patch_states = ["Unpatched", "In Progress", "Patched", "Accepted Risk"]
    vulns = pd.DataFrame([{
        "vuln_id":        i + 1,
        "cve_id":         f"CVE-{random.randint(2020, 2024)}-{random.randint(1000, 99999)}",
        "title":          fake.sentence(nb_words=7).rstrip("."),
        "severity":       random.choices(severities, weights=[10, 25, 40, 25])[0],
        "affected_asset": random.choice(["Web Server", "Database", "VPN Client", "OS Kernel", "Browser", "Email Server"]),
        "discovery_date": _rand_date(date(2022, 1, 1), date(2025, 1, 31)),
        "patch_status":   random.choices(patch_states, weights=[20, 25, 45, 10])[0],
        "risk_score":     round(random.uniform(1.0, 10.0), 1),
    } for i in range(150)])
    _save(vulns, "vulnerabilities")

    # sec_incidents
    categories_si = ["Phishing", "Ransomware", "Data Breach", "Insider Threat", "DDoS"]
    sec_incidents = pd.DataFrame([{
        "incident_id":  i + 1,
        "title":        f"{random.choice(categories_si)} Attempt — {fake.word().title()}",
        "severity":     random.choices(["Critical", "High", "Medium", "Low"], weights=[8, 20, 40, 32])[0],
        "category":     random.choice(categories_si),
        "detected_at":  _rand_dt(date(2022, 1, 1), date(2025, 1, 31)),
        "resolved_at":  None if random.random() < 0.1 else _rand_dt(date(2022, 1, 2), date(2025, 2, 28)),
        "status":       random.choices(["Open", "Investigating", "Contained", "Closed"], weights=[10, 15, 10, 65])[0],
        "assigned_to":  random.choice(["SOC Team", "CISO", "IR Team", "External Vendor"]),
    } for i in range(100)])
    _save(sec_incidents, "sec_incidents")

    # sec_alerts
    alert_types = ["Intrusion Detection", "Malware", "Anomalous Login", "Data Exfiltration", "Policy Violation"]
    alerts = pd.DataFrame([{
        "alert_id":        i + 1,
        "alert_type":      random.choice(alert_types),
        "source":          random.choice(["SIEM", "IDS", "EDR", "WAF", "DLP"]),
        "severity":        random.choices(["Critical", "High", "Medium", "Low"], weights=[8, 20, 40, 32])[0],
        "message":         fake.sentence(),
        "triggered_at":    _rand_dt(date(2024, 1, 1), date(2025, 1, 31)),
        "acknowledged_at": None if random.random() < 0.15 else _rand_dt(date(2024, 1, 1), date(2025, 2, 1)),
        "status":          random.choices(["New", "Acknowledged", "Investigating", "Closed"], weights=[10, 15, 20, 55])[0],
        "asset_id":        random.choice(asset_ids),
    } for i in range(500)])
    _save(alerts, "sec_alerts")

    # security_audits
    audit_types = ["Internal", "External", "Penetration Test", "Compliance Audit"]
    audits = pd.DataFrame([{
        "audit_id":       i + 1,
        "audit_type":     random.choice(audit_types),
        "auditor":        random.choice(["Internal Security Team", "Deloitte", "PwC", "KPMG", "Ernst & Young", "NCC Group"]),
        "start_date":     _rand_date(date(2021, 1, 1), date(2024, 9, 30)),
        "end_date":       _rand_date(date(2024, 10, 1), date(2025, 6, 30)),
        "scope":          random.choice(["Full Infrastructure", "Web Applications", "Cloud Environments", "Network Perimeter", "Endpoints"]),
        "findings_count": random.randint(0, 50),
        "status":         random.choices(["Planned", "In Progress", "Completed", "Report Issued"], weights=[10, 15, 35, 40])[0],
    } for i in range(30)])
    _save(audits, "security_audits")

    # compliance_controls
    frameworks = ["ISO 27001", "SOC 2", "GDPR", "HIPAA", "PCI-DSS"]
    statuses = ["Compliant", "Non-Compliant", "Partially Compliant", "Not Applicable"]
    controls = pd.DataFrame([{
        "control_id":    i + 1,
        "framework":     random.choice(frameworks),
        "control_ref":   f"{random.choice(['A', 'CC', 'Art', 'Req'])}.{random.randint(1,15)}.{random.randint(1,10)}",
        "description":   fake.sentence(),
        "status":        random.choices(statuses, weights=[50, 15, 25, 10])[0],
        "last_assessed": _rand_date(date(2023, 1, 1), date(2025, 1, 31)),
        "assigned_to":   random.choice(["IT Security", "Compliance Team", "Legal", "CISO Office"]),
        "due_date":      _rand_date(date(2025, 1, 1), date(2026, 12, 31)),
    } for i in range(50)])
    _save(controls, "compliance_controls")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def generate() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _sales()
    _it()
    _hr()
    _marketing()
    _security()
    print("\nAll domain data generated successfully.")


if __name__ == "__main__":
    generate()
