"""GENERATE — Security domain: roles, policies, access logs, vulns, incidents, audits."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date, rand_dt
from src.datagen.fixtures import load_fixture
from src.datagen.vocab import values_for


def generate_security(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # sec_roles — reference data in fixtures/sec_roles.json
    roles = pd.DataFrame(load_fixture("sec_roles"))
    tables["sec_roles"] = roles
    role_ids = list(roles["role_id"])

    # sec_policies
    categories_sec = values_for("sec_policies", "category")
    policies = pd.DataFrame([{
        "policy_id":      i + 1,
        "policy_name":    rng.choice(["Acceptable Use Policy", "Password Policy", "Data Retention Policy",
                                      "Remote Access Policy", "Encryption Policy", "BYOD Policy",
                                      "Incident Response Plan", "Vulnerability Management Policy",
                                      "Access Control Policy", "Cloud Security Policy"]),
        "category":       rng.choice(categories_sec),
        "effective_date": rand_date(rng, date(2020, 1, 1), date(2023, 12, 31)),
        "review_date":    rand_date(rng, date(2024, 1, 1), date(2026, 12, 31)),
        "owner":          rng.choice(["CISO", "IT Security", "Legal", "Compliance Team"]),
        "status":         rng.choices(values_for("sec_policies", "status"), weights=[75, 20, 5])[0],
    } for i in range(20)])
    tables["sec_policies"] = policies

    # monitored_assets
    asset_types = values_for("monitored_assets", "asset_type")
    monitored = pd.DataFrame([{
        "asset_id":       i + 1,
        "asset_name":     f"{rng.choice(['srv', 'app', 'db', 'fw', 'vpc'])}-{fake.bothify('??##')}",
        "asset_type":     rng.choice(asset_types),
        "ip_address":     fake.ipv4_private(),
        "criticality":    rng.choices(values_for("monitored_assets", "criticality"), weights=[10, 25, 40, 25])[0],
        "owner":          rng.choice(["Engineering", "IT Ops", "Security", "DevOps"]),
        "last_scan_date": rand_date(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "risk_level":     rng.choice(values_for("monitored_assets", "risk_level")),
    } for i in range(100)])
    tables["monitored_assets"] = monitored
    asset_ids = list(monitored["asset_id"])

    # sec_users
    depts = ["Engineering", "Finance", "HR", "Marketing", "Sales", "Legal", "Operations"]
    sec_users = pd.DataFrame([{
        "user_id":     i + 1,
        "username":    fake.unique.user_name(),
        "email":       fake.unique.company_email(),
        "department":  rng.choice(depts),
        "role_id":     rng.choices(role_ids, weights=[2, 5, 50, 25, 8, 10])[0],
        "created_at":  rand_date(rng, date(2018, 1, 1), date(2024, 6, 30)),
        "last_login":  rand_dt(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "is_active":   rng.choices([1, 0], weights=[90, 10])[0],
        "mfa_enabled": rng.choices([1, 0], weights=[70, 30])[0],
    } for i in range(200)])
    tables["sec_users"] = sec_users
    user_ids = list(sec_users["user_id"])

    # access_logs
    resources = ["/admin/users", "/finance/reports", "/hr/payroll", "/api/data", "/dashboard",
                 "finance-db", "hr-db", "email-server", "/settings", "/audit-logs"]
    actions = values_for("access_logs", "action")
    logs = pd.DataFrame([{
        "log_id":      i + 1,
        "user_id":     rng.choice(user_ids),
        "resource":    rng.choice(resources),
        "action":      rng.choice(actions),
        "ip_address":  fake.ipv4(),
        "timestamp":   rand_dt(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "status":      rng.choices(values_for("access_logs", "status"), weights=[90, 10])[0],
        "device_type": rng.choice(values_for("access_logs", "device_type")),
    } for i in range(2000)])
    tables["access_logs"] = logs

    # vulnerabilities
    severities = values_for("vulnerabilities", "severity")
    patch_states = values_for("vulnerabilities", "patch_status")
    vulns = pd.DataFrame([{
        "vuln_id":        i + 1,
        "cve_id":         f"CVE-{rng.randint(2020, 2024)}-{rng.randint(1000, 99999)}",
        "title":          fake.sentence(nb_words=7).rstrip("."),
        "severity":       rng.choices(severities, weights=[10, 25, 40, 25])[0],
        "affected_asset": rng.choice(["Web Server", "Database", "VPN Client", "OS Kernel", "Browser", "Email Server"]),
        "discovery_date": rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "patch_status":   rng.choices(patch_states, weights=[20, 25, 45, 10])[0],
        "risk_score":     round(rng.uniform(1.0, 10.0), 1),
    } for i in range(150)])
    tables["vulnerabilities"] = vulns

    # sec_incidents
    categories_si = values_for("sec_incidents", "category")
    sec_incidents = pd.DataFrame([{
        "incident_id":  i + 1,
        "title":        f"{rng.choice(categories_si)} Attempt — {fake.word().title()}",
        "severity":     rng.choices(values_for("sec_incidents", "severity"), weights=[8, 20, 40, 32])[0],
        "category":     rng.choice(categories_si),
        "detected_at":  rand_dt(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "resolved_at":  None if rng.random() < 0.1 else rand_dt(rng, date(2022, 1, 2), date(2025, 2, 28)),
        "status":       rng.choices(values_for("sec_incidents", "status"), weights=[10, 15, 10, 65])[0],
        "assigned_to":  rng.choice(["SOC Team", "CISO", "IR Team", "External Vendor"]),
    } for i in range(100)])
    tables["sec_incidents"] = sec_incidents

    # sec_alerts
    alert_types = values_for("sec_alerts", "alert_type")
    alerts = pd.DataFrame([{
        "alert_id":        i + 1,
        "alert_type":      rng.choice(alert_types),
        "source":          rng.choice(["SIEM", "IDS", "EDR", "WAF", "DLP"]),
        "severity":        rng.choices(values_for("sec_alerts", "severity"), weights=[8, 20, 40, 32])[0],
        "message":         fake.sentence(),
        "triggered_at":    rand_dt(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "acknowledged_at": None if rng.random() < 0.15 else rand_dt(rng, date(2024, 1, 1), date(2025, 2, 1)),
        "status":          rng.choices(values_for("sec_alerts", "status"), weights=[10, 15, 20, 55])[0],
        "asset_id":        rng.choice(asset_ids),
    } for i in range(500)])
    tables["sec_alerts"] = alerts

    # security_audits
    audit_types = values_for("security_audits", "audit_type")
    audits = pd.DataFrame([{
        "audit_id":       i + 1,
        "audit_type":     rng.choice(audit_types),
        "auditor":        rng.choice(["Internal Security Team", "Deloitte", "PwC", "KPMG", "Ernst & Young", "NCC Group"]),
        "start_date":     rand_date(rng, date(2021, 1, 1), date(2024, 9, 30)),
        "end_date":       rand_date(rng, date(2024, 10, 1), date(2025, 6, 30)),
        "scope":          rng.choice(["Full Infrastructure", "Web Applications", "Cloud Environments", "Network Perimeter", "Endpoints"]),
        "findings_count": rng.randint(0, 50),
        "status":         rng.choices(values_for("security_audits", "status"), weights=[10, 15, 35, 40])[0],
    } for i in range(30)])
    tables["security_audits"] = audits

    # compliance_controls
    frameworks = values_for("compliance_controls", "framework")
    statuses = values_for("compliance_controls", "status")
    controls = pd.DataFrame([{
        "control_id":    i + 1,
        "framework":     rng.choice(frameworks),
        "control_ref":   f"{rng.choice(['A', 'CC', 'Art', 'Req'])}.{rng.randint(1,15)}.{rng.randint(1,10)}",
        "description":   fake.sentence(),
        "status":        rng.choices(statuses, weights=[50, 15, 25, 10])[0],
        "last_assessed": rand_date(rng, date(2023, 1, 1), date(2025, 1, 31)),
        "assigned_to":   rng.choice(["IT Security", "Compliance Team", "Legal", "CISO Office"]),
        "due_date":      rand_date(rng, date(2025, 1, 1), date(2026, 12, 31)),
    } for i in range(50)])
    tables["compliance_controls"] = controls

    return tables
