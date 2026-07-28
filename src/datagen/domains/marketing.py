"""GENERATE — Marketing domain: campaigns, leads, channels, content, events, metrics."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date, rand_dt


def generate_marketing(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

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
    tables["marketing_channels"] = channels
    chan_ids = list(channels["channel_id"])

    # campaigns
    camp_types = ["Brand Awareness", "Lead Generation", "Product Launch", "Retention"]
    campaigns = pd.DataFrame([{
        "campaign_id":   i + 1,
        "campaign_name": f"{fake.catch_phrase()} Campaign",
        "campaign_type": rng.choice(camp_types),
        "channel_id":    rng.choice(chan_ids),
        "start_date":    rand_date(rng, date(2022, 1, 1), date(2024, 6, 30)),
        "end_date":      rand_date(rng, date(2024, 7, 1), date(2025, 6, 30)),
        "budget":        round(rng.uniform(5_000, 200_000), 2),
        "status":        rng.choices(["Draft", "Active", "Paused", "Completed"], weights=[10, 40, 15, 35])[0],
        "owner":         fake.name(),
    } for i in range(50)])
    tables["campaigns"] = campaigns
    camp_ids = list(campaigns["campaign_id"])

    # leads
    sources = ["Organic Search", "Paid Ad", "Social Media", "Referral", "Event"]
    leads = pd.DataFrame([{
        "lead_id":      i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.email(),
        "source":       rng.choice(sources),
        "campaign_id":  rng.choice(camp_ids),
        "status":       rng.choices(["New", "Contacted", "Qualified", "Converted", "Lost"], weights=[20, 25, 20, 20, 15])[0],
        "created_at":   rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "converted_at": None if rng.random() < 0.7 else rand_date(rng, date(2022, 2, 1), date(2025, 3, 1)),
    } for i in range(1000)])
    tables["leads"] = leads

    # content_assets
    asset_types = ["Blog Post", "Video", "Infographic", "Landing Page", "Whitepaper"]
    content = pd.DataFrame([{
        "asset_id":     i + 1,
        "title":        fake.sentence(nb_words=5).rstrip("."),
        "asset_type":   rng.choice(asset_types),
        "campaign_id":  rng.choice(camp_ids),
        "created_by":   fake.name(),
        "publish_date": rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "status":       rng.choices(["Draft", "In Review", "Published", "Archived"], weights=[10, 15, 60, 15])[0],
    } for i in range(200)])
    tables["content_assets"] = content

    # social_media_posts
    platforms = ["LinkedIn", "Twitter", "Facebook", "Instagram"]
    posts = pd.DataFrame([{
        "post_id":      i + 1,
        "platform":     rng.choice(platforms),
        "content_text": fake.sentence(),
        "campaign_id":  rng.choice(camp_ids),
        "published_at": rand_dt(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "likes":        rng.randint(0, 5000),
        "shares":       rng.randint(0, 500),
        "reach":        rng.randint(100, 100_000),
    } for i in range(300)])
    tables["social_media_posts"] = posts

    # email_campaigns
    emails = pd.DataFrame([{
        "email_id":      i + 1,
        "campaign_id":   rng.choice(camp_ids),
        "subject":       fake.sentence(nb_words=6).rstrip("."),
        "sent_to_count": rng.randint(500, 50_000),
        "open_count":    rng.randint(50, 15_000),
        "click_count":   rng.randint(10, 5_000),
        "bounce_count":  rng.randint(0, 500),
        "sent_at":       rand_dt(rng, date(2022, 1, 1), date(2025, 1, 31)),
    } for i in range(100)])
    tables["email_campaigns"] = emails

    # marketing_events
    event_types = ["Webinar", "Trade Show", "Conference", "Workshop", "Product Demo"]
    events = pd.DataFrame([{
        "event_id":       i + 1,
        "event_name":     f"{fake.company()} {rng.choice(['Summit', 'Forum', 'Expo', 'Workshop'])} {2023 + i % 2}",
        "event_type":     rng.choice(event_types),
        "campaign_id":    rng.choice(camp_ids),
        "start_date":     rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "end_date":       rand_date(rng, date(2025, 2, 1), date(2025, 12, 31)),
        "budget":         round(rng.uniform(2_000, 100_000), 2),
        "attendee_count": rng.randint(10, 5_000),
    } for i in range(30)])
    tables["marketing_events"] = events

    # marketing_budgets
    budgets = pd.DataFrame([{
        "budget_id":        i + 1,
        "campaign_id":      camp_ids[i % len(camp_ids)],
        "period_year":      rng.choice([2022, 2023, 2024]),
        "period_quarter":   rng.randint(1, 4),
        "allocated_amount": round(rng.uniform(5_000, 80_000), 2),
        "spent_amount":     round(rng.uniform(1_000, 80_000), 2),
    } for i in range(200)])
    tables["marketing_budgets"] = budgets

    # customer_segments
    segments = pd.DataFrame([
        {"segment_id": 1,  "segment_name": "High-Value Customers",   "criteria": "Total spend > $5000",          "customer_count": rng.randint(200, 2000),  "created_at": "2023-01-01", "last_updated": "2024-06-01"},
        {"segment_id": 2,  "segment_name": "New Signups",            "criteria": "Signup within last 30 days",   "customer_count": rng.randint(50, 500),   "created_at": "2023-01-01", "last_updated": "2024-12-01"},
        {"segment_id": 3,  "segment_name": "Churned Users",          "criteria": "No purchase in 180 days",      "customer_count": rng.randint(100, 1000), "created_at": "2023-03-01", "last_updated": "2024-11-01"},
        {"segment_id": 4,  "segment_name": "Gold Tier Customers",    "criteria": "loyalty_tier = Gold",          "customer_count": rng.randint(300, 1500), "created_at": "2023-01-01", "last_updated": "2024-10-01"},
        {"segment_id": 5,  "segment_name": "Enterprise Accounts",    "criteria": "Company size > 500 employees", "customer_count": rng.randint(50, 300),   "created_at": "2023-06-01", "last_updated": "2024-09-01"},
        {"segment_id": 6,  "segment_name": "Webinar Attendees",      "criteria": "Attended any webinar event",   "customer_count": rng.randint(100, 800),  "created_at": "2023-07-01", "last_updated": "2024-08-01"},
        {"segment_id": 7,  "segment_name": "Email Clickers",         "criteria": "Clicked email link in 60 days","customer_count": rng.randint(200, 2000), "created_at": "2023-02-01", "last_updated": "2024-12-15"},
        {"segment_id": 8,  "segment_name": "Mobile Users",           "criteria": "Primary device = Mobile",      "customer_count": rng.randint(500, 5000), "created_at": "2023-04-01", "last_updated": "2024-11-30"},
        {"segment_id": 9,  "segment_name": "Discount Seekers",       "criteria": "Purchased with discount > 15%","customer_count": rng.randint(100, 800),  "created_at": "2023-05-01", "last_updated": "2024-10-15"},
        {"segment_id": 10, "segment_name": "Repeat Buyers",          "criteria": "Order count >= 5",             "customer_count": rng.randint(150, 1200), "created_at": "2023-01-01", "last_updated": "2024-12-01"},
    ])
    tables["customer_segments"] = segments

    # campaign_metrics (daily metrics per campaign — 1000 records)
    metrics = pd.DataFrame([{
        "metric_id":          i + 1,
        "campaign_id":        rng.choice(camp_ids),
        "metric_date":        rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "impressions":        rng.randint(1_000, 500_000),
        "clicks":             rng.randint(10, 20_000),
        "conversions":        rng.randint(0, 1_000),
        "revenue_attributed": round(rng.uniform(0, 50_000), 2),
        "ctr":                round(rng.uniform(0.001, 0.15), 4),
    } for i in range(1000)])
    tables["campaign_metrics"] = metrics

    return tables
