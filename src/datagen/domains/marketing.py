"""GENERATE — Marketing domain: campaigns, leads, channels, content, events, metrics."""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
from faker import Faker

from src.datagen.domains._common import rand_date, rand_dt
from src.datagen.fixtures import load_fixture
from src.datagen.vocab import values_for


def generate_marketing(rng: random.Random, fake: Faker) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}

    # marketing_channels — reference data in fixtures/marketing_channels.json
    channels = pd.DataFrame(load_fixture("marketing_channels"))
    tables["marketing_channels"] = channels
    chan_ids = list(channels["channel_id"])

    # campaigns
    camp_types = values_for("campaigns", "campaign_type")
    campaigns = pd.DataFrame([{
        "campaign_id":   i + 1,
        "campaign_name": f"{fake.catch_phrase()} Campaign",
        "campaign_type": rng.choice(camp_types),
        "channel_id":    rng.choice(chan_ids),
        "start_date":    rand_date(rng, date(2022, 1, 1), date(2024, 6, 30)),
        "end_date":      rand_date(rng, date(2024, 7, 1), date(2025, 6, 30)),
        "budget":        round(rng.uniform(5_000, 200_000), 2),
        "status":        rng.choices(values_for("campaigns", "status"), weights=[10, 40, 15, 35])[0],
        "owner":         fake.name(),
    } for i in range(50)])
    tables["campaigns"] = campaigns
    camp_ids = list(campaigns["campaign_id"])

    # leads
    sources = values_for("leads", "source")
    leads = pd.DataFrame([{
        "lead_id":      i + 1,
        "first_name":   fake.first_name(),
        "last_name":    fake.last_name(),
        "email":        fake.unique.email(),
        "source":       rng.choice(sources),
        "campaign_id":  rng.choice(camp_ids),
        "status":       rng.choices(values_for("leads", "status"), weights=[20, 25, 20, 20, 15])[0],
        "created_at":   rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "converted_at": None if rng.random() < 0.7 else rand_date(rng, date(2022, 2, 1), date(2025, 3, 1)),
    } for i in range(1000)])
    tables["leads"] = leads

    # content_assets
    asset_types = values_for("content_assets", "asset_type")
    content = pd.DataFrame([{
        "asset_id":     i + 1,
        "title":        fake.sentence(nb_words=5).rstrip("."),
        "asset_type":   rng.choice(asset_types),
        "campaign_id":  rng.choice(camp_ids),
        "created_by":   fake.name(),
        "publish_date": rand_date(rng, date(2022, 1, 1), date(2025, 1, 31)),
        "status":       rng.choices(values_for("content_assets", "status"), weights=[10, 15, 60, 15])[0],
    } for i in range(200)])
    tables["content_assets"] = content

    # social_media_posts
    platforms = values_for("social_media_posts", "platform")
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
    event_types = values_for("marketing_events", "event_type")
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

    # customer_segments — reference data in fixtures/customer_segments.json;
    # customer_count filled per row from its [lo, hi] range (rng.randint in row order)
    segment_rows = load_fixture("customer_segments")
    for row in segment_rows:
        lo, hi = row["customer_count"]
        row["customer_count"] = rng.randint(lo, hi)
    segments = pd.DataFrame(segment_rows)
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
