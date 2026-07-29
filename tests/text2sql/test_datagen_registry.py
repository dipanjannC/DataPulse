"""Generate-layer seam: injected-seed determinism + registry/schema agreement.

The load-bearing assertion is byte-identity across two ``generate(42)`` calls in
the *same process* — that is what catches a leftover global-RNG reference (a
global advances between calls while the injected rng resets; a subprocess repeat
would mask it by re-seeding on import).
"""

from __future__ import annotations

import pytest

from src.datagen.generate import DATA_DIR, generate
from src.datagen.registry import DOMAIN_GENERATORS
from src.metadata.utils import get_domains, load_schema
from src.quality.validator import validate_dataset


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("datagen")
    a, b, c = base / "seed42_a", base / "seed42_b", base / "seed7"
    generate(seed=42, data_dir=a)
    generate(seed=42, data_dir=b)
    generate(seed=7, data_dir=c)
    return {"a": a, "b": b, "c": c}


def test_same_seed_same_process_is_byte_identical(runs):
    names_a = sorted(p.name for p in runs["a"].glob("*.csv"))
    names_b = sorted(p.name for p in runs["b"].glob("*.csv"))
    assert names_a == names_b
    assert names_a  # something was actually generated
    for name in names_a:
        assert (runs["a"] / name).read_bytes() == (runs["b"] / name).read_bytes(), name


def test_different_seed_changes_output(runs):
    diffs = [
        p.name for p in runs["a"].glob("*.csv")
        if (runs["a"] / p.name).read_bytes() != (runs["c"] / p.name).read_bytes()
    ]
    assert diffs  # at least one table differs under a different seed


def test_registry_covers_every_schema_domain():
    schema_domains = {d["name"] for d in get_domains(load_schema())}
    assert set(DOMAIN_GENERATORS) == schema_domains


def test_domains_subset_generates_only_selected(tmp_path):
    counts = generate(seed=42, domains=["Sales"], data_dir=tmp_path)
    assert {"customers", "orders", "order_items"} <= set(counts)
    assert "employees" not in counts  # an HR table must not appear


def test_generated_data_agrees_with_schema(runs):
    # the pluggable seam's real contract: the generator's output conforms to the
    # catalog (columns, types, PKs) and its referential integrity holds.
    report = validate_dataset(runs["a"], load_schema())
    assert report.schema.passed, [v.to_dict() for v in report.schema.violations]


def test_seed42_reproduces_the_committed_tracked_csvs(runs):
    """The load-bearing determinism guard: a fresh generate(42) must reproduce the
    git-tracked ``src/data/*.csv`` byte-for-byte. Unlike the same-process check
    above (two identical runs), this compares against the COMMITTED bytes, so it
    catches a deterministic-but-wrong perturbation — e.g. an ``allowed_values``
    reorder in schema.json, which now feeds generation and would otherwise slip
    past the schema-conformance and value_domain checks."""
    tracked = sorted(DATA_DIR.glob("*.csv"))
    assert tracked, "no committed CSVs under src/data — determinism guard cannot run"
    for committed in tracked:
        regenerated = runs["a"] / committed.name
        assert regenerated.exists(), f"generator did not produce {committed.name}"
        assert regenerated.read_bytes() == committed.read_bytes(), (
            f"{committed.name} diverged from committed src/data — a generation site's "
            f"draw order was perturbed (e.g. an allowed_values reorder)"
        )
