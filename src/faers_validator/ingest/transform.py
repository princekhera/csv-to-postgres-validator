"""Translate validated DemoRow objects into DemoClean ORM rows.

This is the boundary between the validation layer (Pydantic) and the
storage layer (SQLAlchemy). Keeping it in its own module means changes
to either side don't ripple through the other.
"""

from __future__ import annotations

from uuid import UUID

from ..db.tables import DemoClean
from ..models import DemoRow
from ..partial_date import PartialDate, DatePrecision


def _partial_date_to_columns(pd: PartialDate | None) -> tuple[str | None, str | None, object]:
    """Return (raw, precision, full-date-value-or-None) for storage."""
    if pd is None:
        return None, None, None
    if pd.precision == DatePrecision.DAY:
        from datetime import date
        return pd.raw, pd.precision.value, date(pd.year, pd.month, pd.day)
    return pd.raw, pd.precision.value, None

def to_demo_clean_dict(row: DemoRow, *, ingest_run_id: UUID) -> dict:
    """Build a plain dict matching DemoClean's columns, suitable for bulk insert.

    Faster than building ORM instances when you don't need ORM features
    (relationships, identity map, etc).
    """
    event_raw, event_prec, event_val = _partial_date_to_columns(row.event_dt)
    mfr_raw, mfr_prec, mfr_val = _partial_date_to_columns(row.mfr_dt)
    init_raw, init_prec, init_val = _partial_date_to_columns(row.init_fda_dt)
    fda_raw, fda_prec, fda_val = _partial_date_to_columns(row.fda_dt)
    rept_raw, rept_prec, rept_val = _partial_date_to_columns(row.rept_dt)

    return {
        "primaryid": row.primaryid,
        "caseid": row.caseid,
        "caseversion": row.caseversion,
        "i_f_code": row.i_f_code.value,
        "event_dt": event_raw, "event_dt_precision": event_prec, "event_dt_value": event_val,
        "mfr_dt": mfr_raw, "mfr_dt_precision": mfr_prec, "mfr_dt_value": mfr_val,
        "init_fda_dt": init_raw, "init_fda_dt_precision": init_prec, "init_fda_dt_value": init_val,
        "fda_dt": fda_raw, "fda_dt_precision": fda_prec, "fda_dt_value": fda_val,
        "rept_dt": rept_raw, "rept_dt_precision": rept_prec, "rept_dt_value": rept_val,
        "rept_cod": row.rept_cod.value,
        "auth_num": row.auth_num, "mfr_num": row.mfr_num, "mfr_sndr": row.mfr_sndr,
        "lit_ref": row.lit_ref,
        "age": row.age, "age_cod": row.age_cod.value if row.age_cod else None,
        "age_grp": row.age_grp.value if row.age_grp else None,
        "age_years": row.age_years,
        "sex": row.sex.value if row.sex else None,
        "e_sub": row.e_sub.value,
        "wt": row.wt, "wt_cod": row.wt_cod.value if row.wt_cod else None,
        "weight_kg": row.weight_kg,
        "to_mfr": row.to_mfr.value if row.to_mfr else None,
        "occp_cod": row.occp_cod,
        "reporter_country": row.reporter_country,
        "occr_country": row.occr_country,
        "event_dt_suspect_imputed": row.event_dt_suspect_imputed,
        "age_group_boundary_mismatch": row.age_group_boundary_mismatch,
        "ingest_run_id": ingest_run_id,
    }

# Column order for COPY. Excludes server-generated columns (ingested_at, rejected_at).
DEMO_CLEAN_COLUMNS = [
    "primaryid", "caseid", "caseversion", "i_f_code",
    "event_dt", "event_dt_precision", "event_dt_value",
    "mfr_dt", "mfr_dt_precision", "mfr_dt_value",
    "init_fda_dt", "init_fda_dt_precision", "init_fda_dt_value",
    "fda_dt", "fda_dt_precision", "fda_dt_value",
    "rept_dt", "rept_dt_precision", "rept_dt_value",
    "rept_cod", "auth_num", "mfr_num", "mfr_sndr", "lit_ref",
    "age", "age_cod", "age_grp", "age_years",
    "sex", "e_sub",
    "wt", "wt_cod", "weight_kg",
    "to_mfr", "occp_cod", "reporter_country", "occr_country",
    "event_dt_suspect_imputed", "age_group_boundary_mismatch",
    "ingest_run_id",
]

DEMO_REJECTED_COLUMNS = [
    "primaryid", "raw_data", "errors", "error_summary",
    "source_line_number", "ingest_run_id",
]