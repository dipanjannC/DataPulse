"""GENERATE — HR domain: employees, payroll, performance, leave, recruitment, benefits."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd
from faker import Faker

from text2sql.datagen.domains._common import rand_date


def generate_hr(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # departments (fixed)
    dept_names = ["Engineering", "Finance", "Human Resources", "Marketing", "Sales",
                  "Operations", "Legal", "Product", "Customer Success", "Data & Analytics"]
    departments = pd.DataFrame([{
        "department_id":    i + 1,
        "department_name":  dept_names[i],
        "location":         rng.choice(["New York", "San Francisco", "Chicago", "Austin", "Remote"]),
        "budget":           round(rng.uniform(200_000, 5_000_000), 2),
        "head_employee_id": None,  # updated after employees are generated
    } for i in range(len(dept_names))])
    tables["departments"] = departments
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
        "department_id": rng.choice(dept_ids),
        "level":         rng.choice(levels),
        "min_salary":    round(rng.uniform(40_000, 100_000), 2),
        "max_salary":    round(rng.uniform(100_001, 250_000), 2),
    } for i in range(len(position_titles))])
    tables["positions"] = positions
    pos_ids = list(positions["position_id"])

    # employees
    emp_types = ["Full-Time", "Part-Time", "Contractor", "Intern"]
    employees = pd.DataFrame([{
        "employee_id":     i + 1,
        "first_name":      fake.first_name(),
        "last_name":       fake.last_name(),
        "email":           fake.unique.company_email(),
        "department_id":   rng.choice(dept_ids),
        "position_id":     rng.choice(pos_ids),
        "hire_date":       rand_date(rng, date(2015, 1, 1), date(2024, 6, 30)),
        "employment_type": rng.choices(emp_types, weights=[70, 10, 15, 5])[0],
        "manager_id":      None,  # set below
    } for i in range(300)])
    emp_ids = list(employees["employee_id"])
    # assign managers (each employee has a random senior employee as manager, top 10% are managers)
    manager_pool = emp_ids[:30]
    employees["manager_id"] = [None if i < 10 else rng.choice(manager_pool) for i in range(len(employees))]
    tables["employees"] = employees

    # payroll (last 12 months per employee — sample 300 × 6 periods)
    payroll_rows = []
    for eid in rng.sample(emp_ids, min(300, len(emp_ids))):
        for m in range(1, 7):
            gross = round(rng.uniform(3_000, 18_000), 2)
            ded   = round(gross * rng.uniform(0.20, 0.35), 2)
            payroll_rows.append({
                "payroll_id":   len(payroll_rows) + 1,
                "employee_id":  eid,
                "pay_period":   f"2024-{m:02d}",
                "gross_salary": gross,
                "deductions":   ded,
                "net_salary":   round(gross - ded, 2),
                "payment_date": str(date(2024, m, 28)),
            })
    tables["payroll"] = pd.DataFrame(payroll_rows)

    # leave_requests
    leave_types = ["Annual", "Sick", "Maternity", "Paternity", "Unpaid"]
    leave_rows = []
    for i in range(500):
        sd  = date.fromisoformat(rand_date(rng, date(2023, 1, 1), date(2024, 12, 31)))
        days = rng.randint(1, 15)
        ed  = sd + timedelta(days=days)
        leave_rows.append({
            "leave_id":    i + 1,
            "employee_id": rng.choice(emp_ids),
            "leave_type":  rng.choice(leave_types),
            "start_date":  str(sd),
            "end_date":    str(ed),
            "days_count":  days,
            "status":      rng.choices(["Approved", "Approved", "Pending", "Rejected"], weights=[60, 20, 15, 5])[0],
            "approved_by": rng.choice(manager_pool),
        })
    tables["leave_requests"] = pd.DataFrame(leave_rows)

    # performance_reviews
    reviews = pd.DataFrame([{
        "review_id":     i + 1,
        "employee_id":   rng.choice(emp_ids),
        "reviewer_id":   rng.choice(manager_pool),
        "review_period": rng.choice(["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2023", "Annual 2023"]),
        "rating":        round(rng.uniform(1.5, 5.0), 1),
        "comments":      fake.sentence(),
        "review_date":   rand_date(rng, date(2023, 10, 1), date(2025, 1, 31)),
    } for i in range(300)])
    tables["performance_reviews"] = reviews

    # training_programs
    programs = ["Python for Data Science", "Leadership Essentials", "AWS Cloud Practitioner",
                "Agile & Scrum Fundamentals", "Excel Advanced", "Cybersecurity Awareness",
                "Communication Skills", "Project Management Professional", "SQL Bootcamp", "Design Thinking"]
    training = pd.DataFrame([{
        "training_id":     i + 1,
        "employee_id":     rng.choice(emp_ids),
        "program_name":    rng.choice(programs),
        "provider":        rng.choice(["Coursera", "Udemy", "LinkedIn Learning", "Internal", "Pluralsight"]),
        "start_date":      rand_date(rng, date(2023, 1, 1), date(2024, 6, 30)),
        "completion_date": None if rng.random() < 0.2 else rand_date(rng, date(2023, 2, 1), date(2025, 1, 1)),
        "status":          rng.choices(["Completed", "In Progress", "Enrolled", "Dropped"], weights=[60, 20, 12, 8])[0],
        "cost":            round(rng.uniform(50.0, 3_000.0), 2),
    } for i in range(400)])
    tables["training_programs"] = training

    # employee_benefits
    benefit_types = ["Health", "Dental", "Vision", "Retirement", "Life Insurance"]
    benefits = pd.DataFrame([{
        "benefit_id":            i + 1,
        "employee_id":           rng.choice(emp_ids),
        "benefit_type":          rng.choice(benefit_types),
        "plan_name":             rng.choice(["Blue Cross PPO", "Aetna HMO", "Fidelity 401k", "MetLife Vision", "Prudential Life"]),
        "enrollment_date":       rand_date(rng, date(2018, 1, 1), date(2024, 6, 30)),
        "employer_contribution": round(rng.uniform(100.0, 600.0), 2),
        "employee_contribution": round(rng.uniform(0.0, 300.0), 2),
    } for i in range(600)])
    tables["employee_benefits"] = benefits

    # job_postings
    postings = pd.DataFrame([{
        "posting_id":      i + 1,
        "position_id":     rng.choice(pos_ids),
        "department_id":   rng.choice(dept_ids),
        "posted_date":     rand_date(rng, date(2023, 1, 1), date(2024, 12, 31)),
        "closing_date":    rand_date(rng, date(2024, 1, 1), date(2025, 6, 30)),
        "status":          rng.choices(["Open", "Closed", "On Hold", "Filled"], weights=[30, 25, 10, 35])[0],
        "applicant_count": rng.randint(5, 200),
    } for i in range(50)])
    tables["job_postings"] = postings

    # attendance (sample — 300 employees × 10 days)
    att_rows = []
    for i, eid in enumerate(rng.sample(emp_ids, min(300, len(emp_ids)))):
        for day_offset in range(10):
            d = date(2024, 6, 1) + timedelta(days=day_offset)
            if d.weekday() >= 5:
                continue
            status = rng.choices(["Present", "Absent", "Half Day", "On Leave"], weights=[80, 5, 10, 5])[0]
            check_in  = f"{rng.randint(8, 10):02d}:{rng.randint(0, 59):02d}" if status in ("Present", "Half Day") else None
            check_out = f"{rng.randint(16, 19):02d}:{rng.randint(0, 59):02d}" if status == "Present" else None
            att_rows.append({
                "attendance_id": len(att_rows) + 1,
                "employee_id":   eid,
                "date":          str(d),
                "check_in":      check_in,
                "check_out":     check_out,
                "hours_worked":  round(rng.uniform(4, 9), 1) if status == "Present" else None,
                "status":        status,
            })
    tables["attendance"] = pd.DataFrame(att_rows)

    return tables
