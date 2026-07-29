"""GENERATE — IT domain: vendors, projects, assets, incidents, deployments, tickets."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date, rand_dt
from src.datagen.fixtures import load_fixture
from src.datagen.vocab import values_for


def generate_it(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # it_vendors
    service_types = values_for("it_vendors", "service_type")
    vendors = pd.DataFrame([{
        "vendor_id":      i + 1,
        "vendor_name":    fake.company(),
        "contact_email":  fake.company_email(),
        "service_type":   rng.choice(service_types),
        "contract_start": rand_date(rng, date(2020, 1, 1), date(2023, 6, 30)),
        "contract_end":   rand_date(rng, date(2024, 1, 1), date(2026, 12, 31)),
        "annual_spend":   round(rng.uniform(5_000, 500_000), 2),
    } for i in range(20)])
    tables["it_vendors"] = vendors

    # it_projects
    statuses = values_for("it_projects", "status")
    projects = pd.DataFrame([{
        "project_id":      i + 1,
        "project_name":    f"{fake.bs().title()} System",
        "description":     fake.sentence(),
        "start_date":      rand_date(rng, date(2022, 1, 1), date(2024, 1, 1)),
        "end_date":        rand_date(rng, date(2024, 1, 1), date(2025, 12, 31)),
        "status":          rng.choice(statuses),
        "budget":          round(rng.uniform(10_000, 500_000), 2),
        "project_manager": fake.name(),
    } for i in range(30)])
    tables["it_projects"] = projects
    proj_ids = list(projects["project_id"])

    # sla_definitions — reference data in fixtures/sla_definitions.json
    slas = pd.DataFrame(load_fixture("sla_definitions"))
    tables["sla_definitions"] = slas

    # servers
    envs = values_for("servers", "environment")
    oses = ["Ubuntu 22.04", "Ubuntu 20.04", "Windows Server 2022", "RHEL 9", "CentOS 8"]
    servers = pd.DataFrame([{
        "server_id":   i + 1,
        "hostname":    f"srv-{fake.bothify('??##').lower()}",
        "ip_address":  fake.ipv4_private(),
        "os":          rng.choice(oses),
        "cpu_cores":   rng.choice([4, 8, 16, 32, 64]),
        "ram_gb":      rng.choice([8, 16, 32, 64, 128]),
        "storage_gb":  rng.choice([256, 512, 1024, 2048, 4096]),
        "environment": rng.choice(envs),
        "status":      rng.choices(values_for("servers", "status"), weights=[80, 8, 8, 4])[0],
    } for i in range(50)])
    tables["servers"] = servers

    # it_assets
    asset_types = values_for("it_assets", "asset_type")
    assets = pd.DataFrame([{
        "asset_id":      i + 1,
        "asset_name":    f"{rng.choice(['Dell', 'HP', 'Lenovo', 'Cisco', 'Apple'])} {fake.word().title()}",
        "asset_type":    rng.choice(asset_types),
        "serial_number": fake.bothify("??###-??###-??###"),
        "purchase_date": rand_date(rng, date(2019, 1, 1), date(2024, 1, 1)),
        "purchase_cost": round(rng.uniform(200.0, 5000.0), 2),
        "assigned_to":   fake.user_name(),
        "location":      rng.choice(["HQ Floor 1", "HQ Floor 2", "Data Center", "Remote", "In Storage"]),
        "status":        rng.choices(values_for("it_assets", "status"), weights=[75, 10, 10, 5])[0],
    } for i in range(200)])
    tables["it_assets"] = assets

    # software_licenses
    sw_names = ["Microsoft Office", "Adobe Creative Cloud", "Slack", "Zoom", "Jira", "Confluence", "GitHub Enterprise", "Tableau", "Salesforce", "ServiceNow"]
    licenses = pd.DataFrame([{
        "license_id":    i + 1,
        "software_name": sw_names[i % len(sw_names)],
        "vendor":        rng.choice(["Microsoft", "Adobe", "Atlassian", "Salesforce", "GitHub"]),
        "license_type":  rng.choice(values_for("software_licenses", "license_type")),
        "quantity":      rng.choice([10, 25, 50, 100, 250, 500]),
        "expiry_date":   rand_date(rng, date(2024, 6, 1), date(2027, 12, 31)),
        "cost":          round(rng.uniform(1_000, 100_000), 2),
        "assigned_to":   rng.choice(["Engineering", "Marketing", "Finance", "HR", "All Staff"]),
    } for i in range(50)])
    tables["software_licenses"] = licenses

    # it_incidents
    categories_it = values_for("it_incidents", "category")
    it_incidents = pd.DataFrame([{
        "incident_id": i + 1,
        "title":       fake.sentence(nb_words=6).rstrip("."),
        "severity":    rng.choices(values_for("it_incidents", "severity"), weights=[5, 15, 40, 40])[0],
        "category":    rng.choice(categories_it),
        "status":      rng.choices(values_for("it_incidents", "status"), weights=[10, 20, 30, 40])[0],
        "reported_by": fake.user_name(),
        "assigned_to": fake.user_name(),
        "created_at":  rand_dt(rng, date(2023, 1, 1), date(2025, 1, 1)),
        "resolved_at": None if rng.random() < 0.15 else rand_dt(rng, date(2023, 1, 2), date(2025, 2, 1)),
    } for i in range(300)])
    tables["it_incidents"] = it_incidents
    inc_ids = list(it_incidents["incident_id"])

    # change_requests
    change_requests = pd.DataFrame([{
        "cr_id":        i + 1,
        "title":        f"Update {fake.word().title()} {rng.choice(['Configuration', 'Firmware', 'Policy', 'Access'])}",
        "change_type":  rng.choice(values_for("change_requests", "change_type")),
        "priority":     rng.choice(values_for("change_requests", "priority")),
        "status":       rng.choice(values_for("change_requests", "status")),
        "requested_by": fake.user_name(),
        "approved_by":  fake.user_name() if rng.random() > 0.2 else None,
        "planned_date": rand_date(rng, date(2024, 1, 1), date(2025, 12, 31)),
    } for i in range(100)])
    tables["change_requests"] = change_requests

    # deployments
    deployments = pd.DataFrame([{
        "deployment_id": i + 1,
        "project_id":    rng.choice(proj_ids),
        "environment":   rng.choice(values_for("deployments", "environment")),
        "version":       f"v{rng.randint(1,5)}.{rng.randint(0,9)}.{rng.randint(0,20)}",
        "deployed_at":   rand_dt(rng, date(2023, 1, 1), date(2025, 1, 1)),
        "deployed_by":   fake.user_name(),
        "status":        rng.choices(values_for("deployments", "status"), weights=[80, 12, 8])[0],
    } for i in range(100)])
    tables["deployments"] = deployments

    # it_tickets
    teams = ["Network", "Desktop Support", "Security", "Cloud Ops", "Database"]
    tickets = pd.DataFrame([{
        "ticket_id":     i + 1,
        "incident_id":   rng.choice(inc_ids) if rng.random() < 0.3 else None,
        "ticket_type":   rng.choice(values_for("it_tickets", "ticket_type")),
        "raised_by":     fake.user_name(),
        "assigned_team": rng.choice(teams),
        "priority":      rng.choice(values_for("it_tickets", "priority")),
        "status":        rng.choices(values_for("it_tickets", "status"), weights=[10, 20, 10, 25, 35])[0],
        "created_at":    rand_dt(rng, date(2023, 1, 1), date(2025, 1, 1)),
        "closed_at":     None if rng.random() < 0.2 else rand_dt(rng, date(2023, 1, 2), date(2025, 2, 1)),
    } for i in range(500)])
    tables["it_tickets"] = tickets

    return tables
