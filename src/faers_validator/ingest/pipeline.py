"""Ingest pipeline orchestrator.

One function: `ingest_demo_file`. It reads a CSV, validates each row,
batches clean and rejected rows, bulk-inserts them, and records the
run in `ingest_run`. Errors anywhere result in the run being marked
failed and re-raised — fail loud, fail fast.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..db.tables import DemoRejected, IngestRun
from ..models import DemoRow
from .errors import summarise
from .reader import iter_demo_records
from .transform import to_demo_clean

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5_000


def ingest_demo_file(
    engine: Engine,
    csv_path: Path,
    quarter: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
    """Ingest one FAERS DEMO file into Postgres.

    Returns a summary dict with row counts and the run id.
    """
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
    clean_batch: list = []
    rejected_batch: list = []

    try:
        for line_no, record in iter_demo_records(csv_path):
            rows_seen += 1
            try:
                validated = DemoRow.model_validate(record)
                clean_batch.append(to_demo_clean(validated, ingest_run_id=run_id))
                rows_clean += 1
            except ValidationError as e:
                errors = e.errors()
                primaryid = record.get("primaryid")
                try:
                    primaryid = int(primaryid) if primaryid else None
                except (TypeError, ValueError):
                    primaryid = None

                rejected_batch.append(DemoRejected(
                    primaryid=primaryid,
                    raw_data=record,
                    errors=[{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                            for err in errors],
                    error_summary=summarise(errors),
                    source_line_number=line_no,
                    ingest_run_id=run_id,
                ))
                rows_rejected += 1

            if len(clean_batch) >= batch_size:
                _flush(engine, clean_batch, rejected_batch)
                clean_batch, rejected_batch = [], []

        # Final flush
        if clean_batch or rejected_batch:
            _flush(engine, clean_batch, rejected_batch)

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

    with Session(engine) as session:
        from datetime import datetime, timezone
        run = session.get(IngestRun, run_id)
        run.status = "succeeded"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_seen = rows_seen
        run.rows_clean = rows_clean
        run.rows_rejected = rows_rejected
        session.commit()

    log.info(f"Run {run_id} finished: {rows_clean} clean, {rows_rejected} rejected of {rows_seen}")
    return {
        "run_id": str(run_id),
        "rows_seen": rows_seen,
        "rows_clean": rows_clean,
        "rows_rejected": rows_rejected,
    }


def _flush(engine: Engine, clean_batch: list, rejected_batch: list) -> None:
    """Bulk-insert one batch each of clean and rejected rows."""
    with Session(engine) as session:
        if clean_batch:
            session.add_all(clean_batch)
        if rejected_batch:
            session.add_all(rejected_batch)
        session.commit()