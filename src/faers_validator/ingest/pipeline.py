"""Ingest pipeline orchestrator.

One function: `ingest_demo_file`. It reads a CSV, validates each row,
batches clean and rejected rows, bulk-inserts them, and records the
run in `ingest_run`. Uses Core-level bulk inserts (Session.execute with
a list of dicts) which is ~10× faster than ORM add_all for inserts.
"""

from __future__ import annotations
import json
from sqlalchemy.engine import Connection

from .transform import DEMO_CLEAN_COLUMNS, DEMO_REJECTED_COLUMNS
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import insert

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db.tables import DemoClean, DemoRejected, IngestRun
from ..models import DemoRow
from .errors import summarise
from .reader import iter_demo_records
from .transform import to_demo_clean_dict

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000


def ingest_demo_file(
    engine: Engine,
    csv_path: Path,
    quarter: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Ingest one FAERS DEMO file into Postgres."""
    with Session(engine) as session:
        run = IngestRun(
            source_file=str(csv_path),
            quarter=quarter,
            status="running",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
        log.info(f"Started ingest run {run_id} for {csv_path}")

    rows_seen = 0
    rows_clean = 0
    rows_rejected = 0
    clean_batch: list[dict] = []
    rejected_batch: list[dict] = []

    t_validate = 0.0
    t_transform = 0.0
    t_flush = 0.0
    t_start = time.perf_counter()

    try:
        # Single session for all batches — avoids per-flush connection overhead.
        with Session(engine) as session:
            for line_no, record in iter_demo_records(csv_path):
                rows_seen += 1
                try:
                    t0 = time.perf_counter()
                    validated = DemoRow.model_validate(record)
                    t_validate += time.perf_counter() - t0

                    t0 = time.perf_counter()
                    clean_batch.append(to_demo_clean_dict(validated, ingest_run_id=run_id))
                    t_transform += time.perf_counter() - t0

                    rows_clean += 1
                except ValidationError as e:
                    errors = e.errors()
                    primaryid = record.get("primaryid")
                    try:
                        primaryid = int(primaryid) if primaryid else None
                    except (TypeError, ValueError):
                        primaryid = None

                    rejected_batch.append({
                        "primaryid": primaryid,
                        "raw_data": record,
                        "errors": [
                            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                            for err in errors
                        ],
                        "error_summary": summarise(errors),
                        "source_line_number": line_no,
                        "ingest_run_id": run_id,
                    })
                    rows_rejected += 1

                if len(clean_batch) >= batch_size:
                    t0 = time.perf_counter()
                    _flush(session, clean_batch, rejected_batch)
                    t_flush += time.perf_counter() - t0
                    clean_batch, rejected_batch = [], []

            if clean_batch or rejected_batch:
                t0 = time.perf_counter()
                _flush(session, clean_batch, rejected_batch)
                t_flush += time.perf_counter() - t0

    except Exception as e:
        log.exception("Ingest failed")
        with Session(engine) as session:
            run = session.get(IngestRun, run_id)
            run.status = "failed"
            run.error_message = str(e)
            run.rows_seen = rows_seen
            run.rows_clean = rows_clean
            run.rows_rejected = rows_rejected
            session.commit()
        raise

    total = time.perf_counter() - t_start
    log.info(
        f"Timing: total={total:.1f}s validate={t_validate:.1f}s "
        f"transform={t_transform:.1f}s flush={t_flush:.1f}s "
        f"other={total - t_validate - t_transform - t_flush:.1f}s"
    )

    with Session(engine) as session:
        run = session.get(IngestRun, run_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_seen = rows_seen
        run.rows_clean = rows_clean
        run.rows_rejected = rows_rejected
        session.commit()

    log.info(
        f"Run {run_id} finished: {rows_clean} clean, {rows_rejected} rejected of {rows_seen}"
    )
    return {
        "run_id": str(run_id),
        "rows_seen": rows_seen,
        "rows_clean": rows_clean,
        "rows_rejected": rows_rejected,
    }


def _flush(session: Session, clean_batch: list[dict], rejected_batch: list[dict]) -> None:
    """Bulk-load using Postgres COPY.

    COPY streams binary-encoded rows down a single connection and is
    the fastest way to load bulk data into Postgres. Roughly 10-100×
    faster than INSERT, depending on row size.
    """
    conn: Connection = session.connection()
    raw_conn = conn.connection.dbapi_connection  # the underlying psycopg connection

    if clean_batch:
        _copy_rows(raw_conn, "faers.demo_clean", DEMO_CLEAN_COLUMNS, clean_batch)
    if rejected_batch:
        _copy_rows(raw_conn, "faers.demo_rejected", DEMO_REJECTED_COLUMNS, rejected_batch,
                   json_columns={"raw_data", "errors"})
    session.commit()


def _copy_rows(
    raw_conn,
    table: str,
    columns: list[str],
    rows: list[dict],
    *,
    json_columns: set[str] | None = None,
) -> None:
    """Use psycopg's COPY ... FROM STDIN to stream rows in.

    `json_columns` lists fields that need json.dumps before sending
    (dicts and lists destined for JSONB columns).
    """
    json_columns = json_columns or set()
    col_list = ", ".join(columns)
    sql = f"COPY {table} ({col_list}) FROM STDIN"

    with raw_conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for row in rows:
                values = []
                for col in columns:
                    v = row.get(col)
                    if v is not None and col in json_columns:
                        v = json.dumps(v)
                    values.append(v)
                copy.write_row(values)