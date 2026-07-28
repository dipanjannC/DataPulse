"""Shared date helpers for the per-domain generators.

Every source of randomness is the injected ``rng`` — no module-global RNG — so a
run is fully determined by the seed handed to ``datagen.generate``.
"""

from __future__ import annotations

import random
from datetime import date, timedelta


def rand_date(rng: random.Random, start: date, end: date) -> str:
    return str(start + timedelta(days=rng.randint(0, (end - start).days)))


def rand_dt(rng: random.Random, start: date, end: date) -> str:
    d = start + timedelta(days=rng.randint(0, (end - start).days))
    h, m = rng.randint(0, 23), rng.randint(0, 59)
    return f"{d} {h:02d}:{m:02d}:00"
