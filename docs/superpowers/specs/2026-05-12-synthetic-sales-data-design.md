# Synthetic Sales Data Generation & Quality Review — Design

_Date: 2026-05-12_
_Status: Draft — pending implementation_

## Problem

`src/datagen/` currently contains 9 scripts copied from a KYC project. They import from `src.services.*`, `src.domain.metadata.*`, `src.infrastructure.aws.bedrock_client`, `src.config.bedrock_config`, and `scripts.generate_semantic_values` — none of which exist in this repository. The accompanying `data/sample/synthetic_config.json` is shaped for KYC entities (Customer.External_Identifier_Type, Beneficiary_Type, etc.), not for the DataPulse sales domain.

Net: the datagen module is non-functional scaffolding today. The sales domain itself is well-defined (`Product`, `Customer`, `Order` dataclasses; `ORDER_FIELDS` metadata; `Region` / `Channel` / `ProductCategory` enums; an 8-row `sample_sales.csv`), and there is no working way to produce more of it.

## Goals

1. Produce reproducible, configurable synthetic sales CSVs that match `ORDER_FIELDS` exactly.
2. Evaluate the generated data on two dimensions: **schema conformance** and **distributional realism**.
3. Reuse the layered architecture of the original KYC pipeline (`metadata → mapping → generate → validate`), retargeted to the sales domain.
4. Stay within DDD context rules — `datagen` may depend on `sales_data` domain models, nothing else.
5. Deterministic only — no LLM in this iteration. Same seed + same config → byte-identical CSV.

## Non-goals

- LLM-driven generation (Gemini/Bedrock). Architecture leaves room to add later.
- Downstream graph-construction validation (deferred until `CsvLoader`/`GraphBuilder` are implemented).
- Database loading (`load_synthetic_to_db.py`-style). Out of scope for sales pipeline today.
- Multi-table referential integrity checks (single flat CSV in this iteration).
- DDL generation, semantic-value LLM bootstrap — both deferred.

## Module layout

```
src/datagen/
  __init__.py
  config.py          # SyntheticConfig dataclass + load_config()
  schema.py          # SalesCatalog: builds Customer + Product pools
  generator.py       # OrderGenerator: emits List[Order] obeying distributions
  writer.py          # write_csv(orders, path) — column order from ORDER_FIELDS
  validator.py       # validate(csv_path, config) -> QualityReport
  reports.py         # QualityReport dataclass + JSON serialization
  generate.py        # CLI: uv run python -m src.datagen.generate
  validate.py        # CLI: uv run python -m src.datagen.validate
  _kyc_legacy/       # Archived original scripts (no __init__.py)
```

Responsibilities:

- **schema.py** owns *catalogs* — fixed-size pools of `Customer` and `Product` instances built once per run. Ensures (customer_id, customer_name) and (product_id, product_name, category) are referentially consistent across all rows by construction.
- **generator.py** is the only place that touches randomness for orders. Accepts a seeded `numpy.random.Generator`.
- **writer.py** is the only place that flattens domain models to CSV columns via `ORDER_FIELDS`.
- **validator.py** reads from the written CSV, not in-memory rows — verifies round-trip and allows standalone validation of any CSV.
- **_kyc_legacy/** keeps the original scripts visible as architectural reference. No `__init__.py` so it's not importable; no test or mypy coverage.

Boundary check: `datagen` imports from `sales_data.domain.models` and `sales_data.metadata.{enums,column_definitions}` only. No imports from `graph` or `query_engine`. Both directions match the DDD rules in `.claude/CLAUDE.md`.

## Data flow

```
ORDER_FIELDS + enums.{Region,Channel,ProductCategory}
        │
        ▼
SyntheticConfig (from synthetic_config.json)
        │
        ▼
SalesCatalog (schema.py)         ── deterministic, seeded
        │
        ▼
List[Order] (generator.py)       ── deterministic, seeded
        │
        ▼
data/raw/sales_1k.csv (writer.py)
        │
        ▼
QualityReport (validator.py) ──► data/raw/quality_report.json
```

## Config schema

`synthetic_config.json` (sales-flavored; `synthetic_config.sample.json` is the tracked template):

```json
{
  "row_count": 1000,
  "target": "data/raw/sales_1k.csv",
  "generation": {
    "seed": 42,
    "catalog": {
      "n_customers": 120,
      "n_products_per_category": 8
    },
    "date_range": { "start": "2024-01-01", "end": "2024-12-31" }
  },
  "validation": {
    "enabled": true,
    "report_path": "data/raw/quality_report.json",
    "fail_on_error": false,
    "tolerances": {
      "distribution_chi2_p_min": 0.01,
      "band_violation_rate_max": 0.02
    }
  },
  "controls": {
    "value_distributions": {
      "region":   { "North America": 50, "Europe": 30, "Asia Pacific": 20 },
      "channel":  { "Online": 60, "Retail": 30, "Distributor": 10 },
      "category": { "Electronics": 50, "Stationery": 30, "Furniture": 20 }
    },
    "price_bands": {
      "Electronics": { "min": 15.00, "max": 500.00 },
      "Stationery":  { "min": 1.50,  "max": 25.00  },
      "Furniture":   { "min": 30.00, "max": 800.00 }
    },
    "quantity_distribution": {
      "Electronics": { "min": 1, "max": 5,  "mean": 1.6 },
      "Stationery":  { "min": 1, "max": 20, "mean": 6.0 },
      "Furniture":   { "min": 1, "max": 3,  "mean": 1.2 }
    }
  }
}
```

Notes:
- Weights are arbitrary numbers; the generator normalizes to probabilities.
- `price_bands` and `quantity_distribution` are keyed by category — that's where realism mostly lives.
- `tolerances` drive the validator's pass/fail gate. Loose defaults so 1k rows don't flake.
- `synthetic_config.json` stays gitignored (per CLAUDE.md sensitive-files list); the tracked `.sample.json` ships these defaults.

## Generation algorithm

**Catalog phase** (`schema.py`, runs once per generation):

1. Build `n_customers` `Customer` instances. `customer_name` from `Faker.name()`. IDs as `CUST-{i:04d}`.
2. For each `ProductCategory`, build `n_products_per_category` `Product` instances. Names from a small hand-curated bank per category (~30 names total, inline in `schema.py`). IDs as `PROD-{cat-prefix}-{i:03d}` (e.g. `PROD-ELE-001`).
3. Return `SalesCatalog(customers: list[Customer], products_by_category: dict[ProductCategory, list[Product]])`.

The hand-curated product bank stays inline. If it grows beyond ~50 names, promote it to a JSON resource.

**Order phase** (`generator.py`, one pass over `row_count`):

```python
for i in range(row_count):
    category = rng.choice(categories, p=normalized_category_weights)
    region   = rng.choice(regions,    p=normalized_region_weights)
    channel  = rng.choice(channels,   p=normalized_channel_weights)
    product  = rng.choice(catalog.products_by_category[category])
    customer = rng.choice(catalog.customers)
    qty      = clip(rng.poisson(qty_mean[category]), qty_min, qty_max)
    price    = round(rng.uniform(price_min[category], price_max[category]), 2)
    date     = start + rng.integers(0, n_days)
    yield Order(order_id=f"ORD-{i:06d}", ...)
```

Design notes:
- One `numpy.random.Generator` seeded from `config.generation.seed` drives everything → fully reproducible.
- Categorical draws happen *before* product lookup, so the product is guaranteed to match category — eliminates a class of referential bugs without a post-hoc check.
- Region and channel are independent of category. If we later want cross-correlations (e.g. Electronics skewing Online), add a conditional table.
- Quantity uses clipped Poisson around `mean` so the mean is realistic without forbidding outliers.
- Price is uniform within band. Acceptable for this iteration; log-normal is a possible future improvement.

## Quality evaluation

Two evaluator functions, each producing a structured block in `QualityReport`.

### Schema conformance (`validator.py::check_schema`)

| Check | Method | Failure example |
|---|---|---|
| Column set matches `EXPECTED_COLUMNS` | `set(df.columns) == set(EXPECTED_COLUMNS)` | extra/missing column |
| Column order matches | `list(df.columns) == EXPECTED_COLUMNS` | columns shuffled |
| Dtypes match `ORDER_FIELDS[i].dtype` | per-column coercion test (str/int/float/date) | quantity is float not int |
| Non-null on required fields | `df[col].notna().all()` for `nullable=False` columns | missing order_id |
| `order_id` is unique | `df["order_id"].is_unique` | duplicates |

Returns `SchemaCheck(passed: bool, violations: list[Violation])`. Hard failures override tolerances.

### Distributional realism (`validator.py::check_distributions`)

| Check | Method | Pass criterion |
|---|---|---|
| Region share matches weights | χ² goodness-of-fit (`scipy.stats.chisquare`) | `p > distribution_chi2_p_min` |
| Channel share matches weights | same | same |
| Category share matches weights | same | same |
| Price per category in band | per-row `min ≤ unit_price ≤ max` | violation rate `≤ band_violation_rate_max` |
| Quantity per category in range | per-row `qty_min ≤ quantity ≤ qty_max` | violation rate `≤ band_violation_rate_max` |
| Date range bounds | `df["order_date"].between(start, end).all()` | strict |

χ² fits: categorical observed counts vs. expected proportions, expected count per bucket ≥ 5 at 1k rows.

### Report shape

```json
{
  "summary": {
    "pass": true,
    "schema_pass": true,
    "distribution_pass": true,
    "row_count": 1000,
    "generated_at": "2026-05-12T14:23:00Z"
  },
  "schema": { "passed": true, "violations": [] },
  "distributions": {
    "region":   { "observed": {...}, "expected": {...}, "chi2": 0.82, "p_value": 0.66, "passed": true },
    "channel":  { "...": "..." },
    "category": { "...": "..." },
    "price_bands":   { "violation_rate": 0.000, "passed": true },
    "quantity":      { "violation_rate": 0.000, "passed": true },
    "date_range":    { "passed": true }
  },
  "config_hash": "sha256:..."
}
```

`config_hash` is a stable hash of the normalized config — same config (modulo key order) produces same hash. Lets you tell at a glance which config produced which report.

`fail_on_error`: when true and `summary.pass = false`, the CLI exits non-zero. Off by default so dev runs don't block iteration.

## CLI surface

```
# Generate 1k orders with default config
uv run python -m src.datagen.generate

# Generate with explicit config + seed override
uv run python -m src.datagen.generate --config data/sample/synthetic_config.json --seed 7

# Validate an existing CSV against the config used to make it
uv run python -m src.datagen.validate --csv data/raw/sales_1k.csv --config data/sample/synthetic_config.json

# Validation gate (CI-style)
uv run python -m src.datagen.validate --csv data/raw/sales_1k.csv --fail-on-error
```

Both entries use `argparse` with `BooleanOptionalAction` for `--fail-on-error`, matching the KYC scripts' style.

## Testing

One test file per source module in `tests/datagen/` per CLAUDE.md convention:

| File | Coverage |
|---|---|
| `test_config.py` | `load_config` parses sample JSON; missing required keys raise; tolerances default sensibly |
| `test_schema.py` | catalog sizes match config; product categories match enums; IDs unique |
| `test_generator.py` | row count exact; same seed → identical orders; different seeds differ; all categorical values in enums; (customer_id, customer_name) consistent across rows; (product_id, product_name, category) consistent across rows |
| `test_writer.py` | CSV column order matches `ORDER_FIELDS`; round-trip read returns same orders |
| `test_validator.py` | clean CSV passes; injected schema break → schema_pass=false; injected skewed distribution → distribution_pass=false with low p-value; price-band violation caught |
| `test_reports.py` | report serializes/deserializes; `config_hash` stable under irrelevant key reordering |

The determinism test in `test_generator.py` is the keystone. Distribution validator tests build synthetic CSVs with known skew (e.g. force 90% Online) and assert the χ² check trips. No mocks; in-memory pandas + tempfile CSVs throughout.

## Dependencies

Add via `uv add`:
- `faker` — names
- `scipy` — `chisquare` goodness-of-fit test

`numpy` arrives transitively via `pandas` — no explicit add.

## Other changes

- `.claude/commands/datagen.md`: rewrite to invoke `src.datagen.generate` then `src.datagen.validate`. Drop KYC-specific steps (`ingest_metadata`, `generate_ddl`, `load_synthetic_to_db`).
- `.claude/MEMORY.md`: after implementation, mark datagen as working for the sales domain.
- `data/sample/synthetic_config.sample.json`: replace KYC contents with the sales-flavored template above. The local `synthetic_config.json` (gitignored) gets the same shape.
- Move `src/datagen/*.py` (the 9 KYC scripts) into `src/datagen/_kyc_legacy/`. No `__init__.py` added there so they remain non-importable.

## Verification before done

1. `uv run pytest tests/datagen/` — all green.
2. `uv run python -m src.datagen.generate` — produces a 1k-row CSV in `data/raw/`.
3. `uv run python -m src.datagen.validate` — writes a quality report with `summary.pass = true`.
4. Re-run with same seed — output CSV is byte-identical.
5. `.claude/MEMORY.md` updated.

## Open questions / future work

- Log-normal price within band (richer tails). Defer.
- Cross-correlations (category × channel). Defer until graph-traversal queries surface a need.
- LLM-enriched product/customer names via existing Gemini integration. Architecture supports adding it as a third "mapping" stage; out of scope here.
- Multi-table output (separate `customers.csv`, `products.csv`, `orders.csv`). Current sales CSV is flat-joined; revisit once graph builder needs distinct sources.
