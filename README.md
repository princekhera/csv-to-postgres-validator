# FAERS Validator

A production-style ingest pipeline for the FDA Adverse Event Reporting System (FAERS) quarterly data extracts. Validates rows against domain-aware rules, normalises units, routes good and bad data to separate Postgres tables, and tracks lineage per ingest run.

Built to learn — and demonstrate — the engineering practices that distinguish a data pipeline from a Python script: schema-first design, graded validation, performance instrumentation, idempotent re-runs, and tests that document behaviour.

![tests](https://github.com/princekhera/csv-to-postgres-validator/actions/workflows/ci.yml/badge.svg)

## What it does

FAERS quarterly extracts arrive as pipe-delimited (`$`) latin-1 text files with seven related tables totalling hundreds of MB. This project ingests the `DEMO` (demographics) file:

- Streams the CSV row-by-row (no full-file load)
- Validates each row against a Pydantic model with 12+ data-quality rules, including cross-field consistency checks
- Routes clean rows into `faers.demo_clean` (typed and indexed), rejects into `faers.demo_rejected` (with structured error info), and records the run in `faers.ingest_run`
- Loads via Postgres `COPY ... FROM STDIN` for near-native insert speed
- Supports `--dry-run` (validate without writing) and `--upsert` (idempotent re-ingest)

## Why it's interesting

This isn't a tutorial CSV loader. FAERS is a real-world clinical dataset with the kind of messiness that breaks naive pipelines:

| Data issue | What the validator does about it |
|---|---|
| Partial dates (`2024`, `202403`, `20240315`) | Custom `PartialDate` type preserves the original precision; not silently coerced to a `datetime.date` |
| Age in mixed units (year, month, day, decade) | Normalised to `age_years` on ingest, with raw `(age, age_cod)` preserved alongside |
| `age=23, age_cod=DEC, age_grp=A` (a 230-year-old "Adult") | Cross-field validator catches the contradiction; row routed to rejected with category `age_implausible` |
| `wt=0` sentinel for "unknown weight" | Rejected as `weight_implausible`; not silently stored as 0 kg |
| `reporter_country="COUNTRY NOT SPECIFIED"` | Coerced to NULL on ingest so downstream consumers see standard SQL semantics |
| First-of-period dates (`20240101`) | Annotated `event_dt_suspect_imputed=true` but accepted; downstream analyses can decide whether to filter |

Of 397,224 rows in 2026 Q1, the pipeline classifies 397,179 clean and 45 rejected. Categories:

| Category | Count |
|---|---|
| `weight_implausible` | 30 |
| `age_group_inconsistent` | 7 |
| `age_unit_mismatch` | 5 |
| `age_implausible` | 3 |

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the diagram and component-by-component walkthrough.

## Performance

| Scenario | Time | Throughput |
|---|---|---|
| Fresh ingest, 397,224 rows | **18s** | ~22,000 rows/sec |
| Idempotent re-ingest (`--upsert`) | **22s** | ~18,000 rows/sec |
| Postgres-only floor (`INSERT ... SELECT generate_series`) | 4.5s | — |

Getting there required moving from `Session.add_all` (175s baseline) to `COPY ... FROM STDIN`, after discovering — via Postgres statement logging — that SQLAlchemy was silently falling back to `executemany`. The journey is documented in [`NOTES.md`](NOTES.md) under "Performance notes."

## Quick start

Prerequisites: Docker (for Postgres), Python 3.12, [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/princekhera/csv-to-postgres-validator.git
cd csv-to-postgres-validator
uv sync
docker compose up -d                          # starts Postgres
uv run alembic upgrade head                   # creates the schema
```

Download a quarterly FAERS file:

```bash
mkdir -p data
# Manually download e.g. faers_ascii_2026q1.zip from
# https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html
# and unzip into data/ascii/
```

Run:

```bash
# Dry run — validate without writing
uv run validator ingest --csv data/ascii/DEMO26Q1.txt --quarter 2026Q1 --dry-run

# Real ingest
uv run validator ingest --csv data/ascii/DEMO26Q1.txt --quarter 2026Q1

# Re-ingest idempotently (replaces rows with matching primaryid)
uv run validator ingest --csv data/ascii/DEMO26Q1.txt --quarter 2026Q1 --upsert
```

Query the results:

```bash
docker compose exec -T postgres psql -U dev -d validator <<'EOF'
SELECT status, rows_seen, rows_clean, rows_rejected,
       EXTRACT(EPOCH FROM (finished_at - started_at))::numeric(5,1) AS seconds
FROM faers.ingest_run ORDER BY started_at DESC LIMIT 5;

SELECT error_summary, COUNT(*) FROM faers.demo_rejected
GROUP BY 1 ORDER BY 2 DESC;
EOF
```

## Tests

```bash
uv run pytest -v
```

46 tests across:

- `test_demo_model.py` — Pydantic validators, every rule has a passing + failing case
- `test_errors.py` — error summarisation, including the unknown-error fallback
- `test_transform.py` — Pydantic-to-dict conversion, including type fidelity
- `test_pipeline_integration.py` — end-to-end ingest against a real Postgres container ([`testcontainers`](https://testcontainers-python.readthedocs.io/)), covering happy path, rejection categorisation, lineage, dry-run idempotency, and upsert semantics

Integration tests spin up Postgres in a Docker container; the rest are pure unit tests.

## Design decisions

**Validation as the boundary, not the storage.** The Pydantic model is the contract between "messy input" and "clean output." It owns enums, range checks, cross-field rules, and the `PartialDate` custom type. The SQLAlchemy models in `db/tables.py` know nothing about validation; they only know how to store. A change to validation rules requires no migration; a change to storage requires no rule update. This separation costs one transform function (`to_demo_clean_dict`) and pays back the first time you need to evolve either side independently.

**Graded severity.** Initial design had a single "reject on inconsistency" rule for `age_grp`. Running against real data showed 654 rejections — mostly boundary disagreements like a 12-year-old declared "Adolescent" (band is 13-17). These aren't errors; they're definition disagreements. Split into "strict" (annotate the row but accept it) and "implausible" (reject) bands. Rejection rate dropped from 0.16% to 0.011%, and the rejected rows are now genuinely worth a human's attention.

**Default-fail, opt-in-overwrite.** Re-running an ingest crashes by default on duplicate `primaryid`. `--upsert` enables the staging-table-plus-`ON CONFLICT` path. The destructive operation is available but requires a deliberate flag. Same principle as `git push --force`.

**Lineage on every row.** Every clean and rejected row carries the `ingest_run_id` it came from. The `ingest_run` table records status, timing, and row counts per invocation. Without this, "when did this row appear in the database?" has no answer.

## What I'd do next

Honest list of things I'd add for a real production deployment:

- **Wrap psycopg `UniqueViolation` in `IntegrityError`** so the COPY path raises the same exception class as ORM inserts. Currently the two paths emit different exception types, which is a small but real interface inconsistency.
- **Ingest the other FAERS tables** (`DRUG`, `REAC`, `OUTC`, etc.). All share `primaryid` as the join key, so the schema generalises. The model files would be smaller — fewer cross-field rules — but the pipeline shape is identical.
- **Schema evolution test.** Load a 2014 Q1 file alongside 2026 Q1 to confirm the validator handles schema drift (new columns added in 2014Q3+). I documented this as an open question in NOTES.md but didn't test it.
- **A staging-table path for first ingest too**, optionally. Right now upsert costs ~19% over plain ingest. For very large quarters that gap would compound; benchmarking whether a unified staging path is actually slower would be worth knowing.
- **A Cowork/MCP integration** so analysts can query the data through the same interface they use for spreadsheets.

## Project structure

```
src/faers_validator/
├── enums.py              # FAERS enum types and unit conversions
├── partial_date.py       # Custom date type preserving submitted precision
├── models.py             # Pydantic DemoRow with all validators
├── cli.py                # Typer CLI: ingest command, --dry-run, --upsert
├── db/
│   ├── engine.py         # SQLAlchemy engine factory
│   └── tables.py         # SQLAlchemy ORM (DemoClean, DemoRejected, IngestRun)
└── ingest/
    ├── reader.py         # Chunked CSV reader
    ├── errors.py         # Pydantic error → category mapping
    ├── transform.py      # DemoRow → dict for COPY
    └── pipeline.py       # Orchestrator + COPY-based bulk loader

tests/
├── conftest.py           # testcontainers Postgres fixture, schema setup
├── fixtures/
│   └── demo_tiny.txt     # 6-row synthetic FAERS file exercising each code path
├── test_demo_model.py
├── test_errors.py
├── test_transform.py
└── test_pipeline_integration.py

alembic/
└── versions/             # Versioned schema migrations
```