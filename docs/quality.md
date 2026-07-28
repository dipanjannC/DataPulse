# Quality Layer

The `src/quality/` layer validates generated data against the catalog before it is loaded. It
is pure over the schema + CSVs — no DB, no network — so it runs anywhere and is unit-tested with
crafted DataFrames.

## What it checks

Driven entirely by `schema.json` (via `metadata/utils.py`):

**Schema conformance** (per table, per column):
- every declared column is present;
- values are consistent with the declared type (`INTEGER`/`REAL`/`DATE`/`DATETIME`; `TEXT` accepts anything);
- primary keys are unique and non-null;
- `nullable: false` is honored (no NULLs).

**Referential integrity** (across all 40 FK edges): every **non-null** FK value resolves to a
parent key. NULLs in nullable FKs are skipped (a NULL means "no parent"). Self-referential FKs
(`categories.parent_category_id`, `employees.manager_id`) are in scope. This is genuinely new
enforcement — the SQLite DDL emits no `REFERENCES`, so nothing else checks it.

**Deliberately skipped:** chi-square distributional checks. `schema.json` declares no expected
distributions, and they would pull in `scipy`, which this lean deploy omits. `distributions` is
emitted empty — a documented deferral, not an oversight.

## Why the dtype checks differ from `src`

`quality/reports.py` is a **verbatim copy** of `src/datagen/reports.py` (copy, not import — the codebase
imports nothing from the other `src/` contexts). The *validator*, though, adapts src's mechanisms for a CSV round-trip:

- A **nullable INTEGER** column is read back by pandas as `float64` (a single NULL forces the float
  dtype), so a naive `is_integer_dtype` check would false-positive on every nullable FK. The checker
  instead accepts whole-valued floats.
- **TEXT** is intentionally vacuous — a CSV round-trip erases the text/number distinction, so any
  value is a valid TEXT value; the real constraint (non-null) is carried by the null check.

Getting this right is what makes the discovery run trustworthy: on the committed data it reports
**0 violations**, so a future violation is a real signal.

## The report

`validate_dataset(data_dir, schema=None) -> QualityReport` reads the CSVs and delegates to
`validate_frames(frames, schema)` (the pure core used by tests). Shape:

```python
QualityReport(
  summary = { "pass", "schema_pass", "referential_integrity_pass",
              "table_count", "total_rows", "violation_count", "row_counts", "generated_at" },
  schema  = SchemaCheck(passed: bool, violations: list[Violation]),
  distributions = {},          # chi-square deliberately skipped
  config_hash = "sha256:...",  # structural hash of the schema (cosmetic edits don't churn it)
)
```

`Violation(kind, field, detail)` kinds: `missing_table`, `missing_column`, `dtype`, `null`,
`duplicate` (PK), `referential_integrity`. `report.schema.passed` is the single overall gate
(true only when there are zero violations of any kind).

## The gate

`pipeline.py` runs validation between GENERATE and LOAD and writes `data/quality_report.json`
(gitignored — read it to see what was checked). The enforcement decision is a pure helper:

```python
_should_abort(report, fail_on_error) == fail_on_error and not report.schema.passed
```

- **Default (warn-only):** log violations, continue. The first validation of freshly generated data
  is a discovery step and must not hold setup hostage.
- **`--fail-on-error`:** abort before load on any violation — flip this on once the data is known clean.

## Run it

```bash
# as part of the pipeline
uv run python -m src.pipeline                 # warn-only
uv run python -m src.pipeline --fail-on-error # hard gate

# standalone, in code
python -c "from src.quality.validator import validate_dataset; \
           r = validate_dataset('src/data'); print(r.summary)"
```

Tests: `tests/text2sql/test_quality_validator.py` (each failure kind + RI, on tiny in-memory
schemas), `test_reports.py` (serialization), `test_pipeline.py` (the gate decision).
