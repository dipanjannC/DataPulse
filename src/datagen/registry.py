"""GENERATE — the domain-generator registry (the pluggable seam).

Add a domain = add a module under ``domains/`` exposing a ``DomainGenerator``
and register it here. The keys MUST match the domain names in
``metadata/schema.json`` (see ``get_domains``) — the quality gate is what
verifies the generator and the schema agree.
"""

from __future__ import annotations

import random
from collections.abc import Callable

import pandas as pd
from faker import Faker

from src.datagen.domains.hr import generate_hr
from src.datagen.domains.it import generate_it
from src.datagen.domains.marketing import generate_marketing
from src.datagen.domains.sales import generate_sales
from src.datagen.domains.security import generate_security

# table_name -> rows, given an injected (rng, faker)
DomainGenerator = Callable[[random.Random, Faker], dict[str, pd.DataFrame]]

DOMAIN_GENERATORS: dict[str, DomainGenerator] = {
    "Sales": generate_sales,
    "IT": generate_it,
    "HR": generate_hr,
    "Marketing": generate_marketing,
    "Security": generate_security,
}
