"""End-to-end integration tests for the ingest pipeline.

These tests use a real Postgres container (via testcontainers) to verify
the pipeline correctly routes rows, records lineage, and handles errors.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from faers_validator.ingest.pipeline import ingest_demo_file


def test_ingest_tiny_fixture(clean_db, tiny_csv):
    """The 6-row fixture: 2 clean (one with annotation), 4 rejected."""
    result = ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    assert result["rows_seen"] == 6
    assert result["rows_clean"] == 2
    assert result["rows_rejected"] == 4

    with clean_db.begin() as conn:
        clean_count = conn.execute(text("SELECT COUNT(*) FROM faers.demo_clean")).scalar()
        rej_count = conn.execute(text("SELECT COUNT(*) FROM faers.demo_rejected")).scalar()

    assert clean_count == 2
    assert rej_count == 4


def test_rejection_categories(clean_db, tiny_csv):
    """Each rejection should be categorised by its primary failure mode."""
    ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        rows = conn.execute(
            text("SELECT primaryid, error_summary FROM faers.demo_rejected ORDER BY primaryid")
        ).fetchall()

    summaries = {r.primaryid: r.error_summary for r in rows}

    # Each rejection is bound to a specific primaryid, so we assert exact mappings.
    # 100000003 fails age_implausible (230 years) BEFORE age_group_inconsistent
    # is checked — single-field validator runs first.
    assert summaries[100000002] == "weight_implausible"
    assert summaries[100000003] == "age_implausible"
    assert summaries[100000004] == "age_unit_mismatch"
    assert summaries[100000006] == "age_group_inconsistent"


def test_annotations_set_on_clean_rows(clean_db, tiny_csv):
    """The 12-year-old declared Adolescent should be clean with the
    age_group_boundary_mismatch annotation set."""
    ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        row = conn.execute(text(
            "SELECT primaryid, age_years, age_grp, age_group_boundary_mismatch "
            "FROM faers.demo_clean WHERE primaryid = 100000005"
        )).fetchone()

    assert row is not None
    assert row.age_years == 12.0
    assert row.age_grp == "T"
    assert row.age_group_boundary_mismatch is True

def test_ingest_run_records_lineage(clean_db, tiny_csv):
    result = ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        run = conn.execute(text(
            "SELECT id, status, rows_seen, rows_clean, rows_rejected, "
            "       finished_at IS NOT NULL AS has_finished_at "
            "FROM faers.ingest_run"
        )).fetchone()

    assert str(run.id) == result["run_id"]
    assert run.status == "succeeded"
    assert run.rows_seen == 6
    assert run.rows_clean == 2
    assert run.rows_rejected == 4
    assert run.has_finished_at


def test_clean_rows_linked_to_ingest_run(clean_db, tiny_csv):
    """Every clean row's ingest_run_id should match the run."""
    result = ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        distinct_runs = conn.execute(text(
            "SELECT DISTINCT ingest_run_id::text FROM faers.demo_clean"
        )).fetchall()

    assert len(distinct_runs) == 1
    assert distinct_runs[0][0] == result["run_id"]


def test_rejected_rows_preserve_raw_data(clean_db, tiny_csv):
    """The raw_data column should contain the original row dict for any rejected row."""
    ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        # Pick the DEC miscoding row by primaryid
        row = conn.execute(text(
            "SELECT raw_data FROM faers.demo_rejected WHERE primaryid = 100000003"
        )).fetchone()

    assert row is not None
    raw = row.raw_data
    assert raw["primaryid"] == "100000003"
    assert raw["age"] == "23"
    assert raw["age_cod"] == "DEC"


def test_source_line_number_recorded(clean_db, tiny_csv):
    """Each rejected row should carry its line number in the source file."""
    ingest_demo_file(clean_db, tiny_csv, quarter="TEST")

    with clean_db.begin() as conn:
        lines = conn.execute(text(
            "SELECT primaryid, source_line_number FROM faers.demo_rejected "
            "ORDER BY source_line_number"
        )).fetchall()

    # Header is line 1, so primaryid=100000002 is at line 3 (second data row)
    assert lines[0].primaryid == 100000002
    assert lines[0].source_line_number == 3

def test_dry_run_validates_without_writing(engine, tiny_csv):
    """Dry run should produce correct counts without touching tables."""
    # Don't use clean_db — we want to verify no writes by comparing before/after
    with engine.begin() as conn:
        before_clean = conn.execute(text("SELECT COUNT(*) FROM faers.demo_clean")).scalar()
        before_rej = conn.execute(text("SELECT COUNT(*) FROM faers.demo_rejected")).scalar()
        before_runs = conn.execute(text("SELECT COUNT(*) FROM faers.ingest_run")).scalar()

    result = ingest_demo_file(engine, tiny_csv, quarter="TEST", dry_run=True)

    with engine.begin() as conn:
        after_clean = conn.execute(text("SELECT COUNT(*) FROM faers.demo_clean")).scalar()
        after_rej = conn.execute(text("SELECT COUNT(*) FROM faers.demo_rejected")).scalar()
        after_runs = conn.execute(text("SELECT COUNT(*) FROM faers.ingest_run")).scalar()

    assert result["dry_run"] is True
    assert result["rows_seen"] == 6
    assert result["rows_clean"] == 2
    assert result["rows_rejected"] == 4
    assert after_clean == before_clean
    assert after_rej == before_rej
    assert after_runs == before_runs

def test_double_ingest_without_upsert_fails(clean_db, tiny_csv):
    """Re-ingesting the same file should fail on the primary key constraint
    unless --upsert is given."""
    from psycopg.errors import UniqueViolation
    from sqlalchemy.exc import IntegrityError

    ingest_demo_file(clean_db, tiny_csv, quarter="TEST")
    with pytest.raises((IntegrityError, UniqueViolation)):
        ingest_demo_file(clean_db, tiny_csv, quarter="TEST")


def test_double_ingest_with_upsert_replaces_rows(clean_db, tiny_csv):
    """Re-ingesting with --upsert should leave the same number of clean rows
    (no duplicates), with the latest ingest_run_id on every row."""
    first = ingest_demo_file(clean_db, tiny_csv, quarter="TEST", upsert=True)
    second = ingest_demo_file(clean_db, tiny_csv, quarter="TEST", upsert=True)

    assert first["run_id"] != second["run_id"]

    with clean_db.begin() as conn:
        clean_count = conn.execute(text("SELECT COUNT(*) FROM faers.demo_clean")).scalar()
        latest_run_count = conn.execute(text(
            "SELECT COUNT(*) FROM faers.demo_clean WHERE ingest_run_id::text = :rid"
        ), {"rid": second["run_id"]}).scalar()
        rej_count = conn.execute(text("SELECT COUNT(*) FROM faers.demo_rejected")).scalar()

    assert clean_count == 2
    assert latest_run_count == 2
    assert rej_count == 8  # 4 rejections × 2 runs, append-only


def test_upsert_updates_changed_fields(clean_db, tiny_csv, tmp_path):
    """When a row's content changes between ingests, upsert should reflect
    the new values. Modify row 100000001 from age=45 (Adult) to age=99 (Elderly)."""
    ingest_demo_file(clean_db, tiny_csv, quarter="TEST", upsert=True)

    original = tiny_csv.read_text()
    modified = original.replace(
        "100000001$10000000$1$I$20240315$20240316$20240320$20240325$EXP$$$PFIZER$$45$YR$A$F$Y$70$KG",
        "100000001$10000000$1$I$20240315$20240316$20240320$20240325$EXP$$$PFIZER$$99$YR$E$F$Y$70$KG",
    )
    modified_path = tmp_path / "demo_modified.txt"
    modified_path.write_text(modified)

    ingest_demo_file(clean_db, modified_path, quarter="TEST", upsert=True)

    with clean_db.begin() as conn:
        row = conn.execute(text(
            "SELECT age, age_grp, age_years FROM faers.demo_clean WHERE primaryid = 100000001"
        )).fetchone()

    assert row.age == 99.0
    assert row.age_grp == "E"
    assert row.age_years == 99.0
