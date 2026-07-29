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
  distributions = {},          # chi-square deliberately skipped (graded distributions)
  profile = { table: {...} },  # descriptive per-column profile (see below) — described, not graded
  config_hash = "sha256:...",  # structural hash of the schema (cosmetic edits don't churn it)
)
```

`Violation(kind, field, detail)` kinds: `missing_table`, `missing_column`, `dtype`, `null`,
`duplicate` (PK), `referential_integrity`. `report.schema.passed` is the single overall gate
(true only when there are zero violations of any kind).

## Profiling & the Data Quality panel

`quality/profiler.py` (`profile_frames(frames, schema)`) adds a **descriptive** per-table /
per-column profile alongside the gate — the answer to "what does this generated data actually
look like?" rather than just "is it valid?". Scipy-free, pure over the frames, driven by each
column's declared role:

- **completeness** (`nulls`, `null_pct`) and **cardinality** (`distinct`, `distinct_pct`) for every column;
- **numeric** (`INTEGER`/`REAL`): min/max/mean/std/quartiles + a small `histogram`;
- **categorical** (declared `allowed_values`) and low-cardinality text: top-N frequency, plus
  `unused` — declared vocabulary that never appears (a real signal the generator under-samples it);
- **datetime**: observed min/max range;
- **key**/**reference** (PK/FK): distinctness / referenced-parent counts.

Every value is a native JSON scalar (numpy types and `NaN` are coerced), so the profile serializes
straight to the API. It is **described, not graded**: there is still no goodness-of-fit test, because
the generator declares no expected distribution to grade against (see the deferral above) — we can
show the observed shape, not gate on an expected one.

**Surfaced live in the app.** `GET /api/quality` (in `src/api/main.py`) returns the validator verdict
+ profile, computed over `src/data/` and cached on a CSV-mtime signature (read-only — never perturbs
generation). The frontend **Data Quality** panel (`frontend/quality.{css,js}`, opened from the sidebar
button) renders it: verdict tiles, an honest framing note, and domain-grouped tables with per-column
completeness meters, categorical bars, and numeric histograms. `tests/text2sql/test_profiler.py`
covers the per-role stats, null/cardinality accounting, and the JSON-safety guarantee.

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
