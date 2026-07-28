"""GENERATE — Security domain: roles, policies, access logs, vulns, incidents, audits."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date, rand_dt


def generate_security(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # sec_roles (fixed)
    roles = pd.DataFrame([
        {"role_id": 1, "role_name": "Admin",       "description": "Full system access",              "permission_level": 5, "created_at": "2020-01-01"},
        {"role_id": 2, "role_name": "Power User",  "description": "Elevated read/write access",      "permission_level": 4, "created_at": "2020-01-01"},
        {"role_id": 3, "role_name": "Standard",    "description": "Standard read/write access",      "permission_level": 3, "created_at": "2020-01-01"},
        {"role_id": 4, "role_name": "Read-Only",   "description": "View-only access to most systems","permission_level": 2, "created_at": "2020-01-01"},
        {"role_id": 5, "role_name": "Auditor",     "description": "Audit and compliance access",     "permission_level": 2, "created_at": "2020-01-01"},
        {"role_id": 6, "role_name": "Guest",       "description": "Minimal temporary access",        "permission_level": 1, "created_at": "2020-01-01"},
    ])
    tables["sec_roles"] = roles
    role_ids = list(roles["role_id"])

    # sec_policies
    categories_sec = ["Access Control", "Data Protection", "Incident Response", "Compliance"]
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
        "status":         rng.choices(["Active", "Under Review", "Retired"], weights=[75, 20, 5])[0],
    } for i in range(20)])
    tables["sec_policies"] = policies

    # monitored_assets
    asset_types = ["Server", "Endpoint", "Network Device", "Cloud Resource", "Application"]
    monitored = pd.DataFrame([{
        "asset_id":       i + 1,
        "asset_name":     f"{rng.choice(['srv', 'app', 'db', 'fw', 'vpc'])}-{fake.bothify('??##')}",
        "asset_type":     rng.choice(asset_types),
        "ip_address":     fake.ipv4_private(),
        "criticality":    rng.choices(["Critical", "High", "Medium", "Low"], weights=[10, 25, 40, 25])[0],
        "owner":          rng.choice(["Engineering", "IT Ops", "Security", "DevOps"]),
        "last_scan_date": rand_date(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "risk_level":     rng.choice(["High", "Medium", "Low"]),
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
    actions = ["Login", "Logout", "Read", "Write", "Delete", "Export"]
    logs = pd.DataFrame([{
        "log_id":      i + 1,
        "user_id":     rng.choice(user_ids),
        "resource":    rng.choice(resources),
        "action":      rng.choice(actions),
        "ip_address":  fake.ipv4(),
        "timestamp":   rand_dt(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "status":      rng.choices(["Success", "Failure"], weights=[90, 10])[0],
        "device_type": rng.choice(["Desktop", "Mobile", "Server"]),
    } for i in range(2000)])
    tables["access_logs"] = logs

    # vulnerabilities
    severities = ["Critical", "High", "Medium", "Low"]
    patch_states = ["Unpatched", "In Progress", "Patched", "Accepted Risk"]
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
    categories_si = ["Phishing", "Ransomware", "Data Breach", "Insider Threat", "DDoS"]
    sec_incidents = pd.DataFrame([{
        "incident_id":  i + 1,
        "title":        f"{rng.choice(categories_si)} Attempt — {fake.word().title()}",
        "severity":     rng.choices(["Critical", "High", "Medium", "Low"], weights=[8, 20, 40, 32])[0],
        "category":     rng.choice(categories_si),
        "detected_at":  rand_dt(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "resolved_at":  None if rng.random() < 0.1 else rand_dt(rng, date(2022, 1, 2), date(2025, 2, 28)),
        "status":       rng.choices(["Open", "Investigating", "Contained", "Closed"], weights=[10, 15, 10, 65])[0],
        "assigned_to":  rng.choice(["SOC Team", "CISO", "IR Team", "External Vendor"]),
    } for i in range(100)])
    tables["sec_incidents"] = sec_incidents

    # sec_alerts
    alert_types = ["Intrusion Detection", "Malware", "Anomalous Login", "Data Exfiltration", "Policy Violation"]
    alerts = pd.DataFrame([{
        "alert_id":        i + 1,
        "alert_type":      rng.choice(alert_types),
        "source":          rng.choice(["SIEM", "IDS", "EDR", "WAF", "DLP"]),
        "severity":        rng.choices(["Critical", "High", "Medium", "Low"], weights=[8, 20, 40, 32])[0],
        "message":         fake.sentence(),
        "triggered_at":    rand_dt(rng, date(2024, 1, 1), date(2025, 1, 31)),
        "acknowledged_at": None if rng.random() < 0.15 else rand_dt(rng, date(2024, 1, 1), date(2025, 2, 1)),
        "status":          rng.choices(["New", "Acknowledged", "Investigating", "Closed"], weights=[10, 15, 20, 55])[0],
        "asset_id":        rng.choice(asset_ids),
    } for i in range(500)])
    tables["sec_alerts"] = alerts

    # security_audits
    audit_types = ["Internal", "External", "Penetration Test", "Compliance Audit"]
    audits = pd.DataFrame([{
        "audit_id":       i + 1,
        "audit_type":     rng.choice(audit_types),
        "auditor":        rng.choice(["Internal Security Team", "Deloitte", "PwC", "KPMG", "Ernst & Young", "NCC Group"]),
        "start_date":     rand_date(rng, date(2021, 1, 1), date(2024, 9, 30)),
        "end_date":       rand_date(rng, date(2024, 10, 1), date(2025, 6, 30)),
        "scope":          rng.choice(["Full Infrastructure", "Web Applications", "Cloud Environments", "Network Perimeter", "Endpoints"]),
        "findings_count": rng.randint(0, 50),
        "status":         rng.choices(["Planned", "In Progress", "Completed", "Report Issued"], weights=[10, 15, 35, 40])[0],
    } for i in range(30)])
    tables["security_audits"] = audits

    # compliance_controls
    frameworks = ["ISO 27001", "SOC 2", "GDPR", "HIPAA", "PCI-DSS"]
    statuses = ["Compliant", "Non-Compliant", "Partially Compliant", "Not Applicable"]
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
