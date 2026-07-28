"""GENERATE — thin runner over the per-domain registry.

Builds a per-run seeded ``random.Random`` + ``Faker`` and hands both to each
registered ``DomainGenerator``, then writes one CSV per returned table. Seeding
is per-run and injected — there is no module-global RNG — so two ``generate(seed)``
calls in the same process produce byte-identical CSVs. (This adopts src's
determinism *discipline* with text2sql's toolset: stdlib ``random`` + Faker
``seed_instance``, not numpy's ``Generator``.)

Output goes to ``src/data/`` — one CSV per table.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from faker import Faker

from src.datagen.registry import DOMAIN_GENERATORS

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


def generate(
    seed: int = 42,
    domains: list[str] | None = None,
    data_dir: Path | str = DATA_DIR,
) -> dict[str, int]:
    """Generate CSVs for the registered domains (optionally a subset).

    Returns a ``{table_name: row_count}`` map. Fully determined by ``seed``.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    if domains is None:
        selected = DOMAIN_GENERATORS
    else:
        selected = {name: DOMAIN_GENERATORS[name] for name in domains}

    row_counts: dict[str, int] = {}
    for domain_name, generator in selected.items():
        for table_name, df in generator(rng, fake).items():
            # Force LF so output is byte-identical across platforms (pandas would
            # otherwise emit CRLF on Windows), keeping the determinism guarantee
            # and the tracked CSVs stable regardless of who regenerates them.
            df.to_csv(data_dir / f"{table_name}.csv", index=False, lineterminator="\n")
            row_counts[table_name] = len(df)
            logger.info("Generated %6d rows  %-30s (%s)", len(df), table_name, domain_name)
    return row_counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    counts = generate()
    logger.info("All domain data generated: %d tables, %d rows", len(counts), sum(counts.values()))
