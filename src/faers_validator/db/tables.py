"""SQLAlchemy ORM models for FAERS tables.

These are the database-side counterparts to the Pydantic models in
`models.py`. The Pydantic models validate the data; these tables store it.
We keep them separate because they have different concerns: Pydantic
enforces the contract at the boundary, SQLAlchemy describes the storage.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "faers"


class Base(DeclarativeBase):
    """Base class for all ORM models. All tables live in the `faers` schema."""

    metadata_schema = SCHEMA  # for documentation only; schema set per-table below


class IngestRun(Base):
    __tablename__ = "ingest_run"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    quarter: Mapped[str] = mapped_column(String(6), nullable=False)  # "2026Q1"
    rows_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_clean: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="running", nullable=False,
    )  # running | succeeded | failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DemoClean(Base):
    __tablename__ = "demo_clean"
    __table_args__ = (
        Index("ix_demo_clean_caseid", "caseid"),
        Index("ix_demo_clean_reporter_country", "reporter_country"),
        Index("ix_demo_clean_event_dt_value", "event_dt_value"),
        {"schema": SCHEMA},
    )

    # Identifiers
    primaryid: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caseid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caseversion: Mapped[int] = mapped_column(Integer, nullable=False)
    i_f_code: Mapped[str] = mapped_column(String(1), nullable=False)

    # Dates — three columns per date field (raw, precision, parsed-value)
    event_dt: Mapped[str | None] = mapped_column(String(8), nullable=True)
    event_dt_precision: Mapped[str | None] = mapped_column(
        String(5), nullable=True,
    )  # year | month | day
    event_dt_value: Mapped[date | None] = mapped_column(Date, nullable=True)

    mfr_dt: Mapped[str | None] = mapped_column(String(8), nullable=True)
    mfr_dt_precision: Mapped[str | None] = mapped_column(String(5), nullable=True)
    mfr_dt_value: Mapped[date | None] = mapped_column(Date, nullable=True)

    init_fda_dt: Mapped[str | None] = mapped_column(String(8), nullable=True)
    init_fda_dt_precision: Mapped[str | None] = mapped_column(String(5), nullable=True)
    init_fda_dt_value: Mapped[date | None] = mapped_column(Date, nullable=True)

    fda_dt: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fda_dt_precision: Mapped[str | None] = mapped_column(String(5), nullable=True)
    fda_dt_value: Mapped[date | None] = mapped_column(Date, nullable=True)

    rept_dt: Mapped[str | None] = mapped_column(String(8), nullable=True)
    rept_dt_precision: Mapped[str | None] = mapped_column(String(5), nullable=True)
    rept_dt_value: Mapped[date | None] = mapped_column(Date, nullable=True)

    rept_cod: Mapped[str] = mapped_column(String(8), nullable=False)

    # Free-text optional fields
    auth_num: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfr_num: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfr_sndr: Mapped[str] = mapped_column(Text, nullable=False)
    lit_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Age (raw + derived)
    age: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_cod: Mapped[str | None] = mapped_column(String(3), nullable=True)
    age_grp: Mapped[str | None] = mapped_column(String(1), nullable=True)
    age_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    sex: Mapped[str | None] = mapped_column(String(1), nullable=True)
    e_sub: Mapped[str] = mapped_column(String(1), nullable=False)

    # Weight (raw + derived)
    wt: Mapped[float | None] = mapped_column(Float, nullable=True)
    wt_cod: Mapped[str | None] = mapped_column(String(3), nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    to_mfr: Mapped[str | None] = mapped_column(String(1), nullable=True)
    occp_cod: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Geography
    reporter_country: Mapped[str | None] = mapped_column(String(32), nullable=True)
    occr_country: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Annotations
    event_dt_suspect_imputed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    age_group_boundary_mismatch: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    # Lineage
    ingest_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.id"),
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class DemoRejected(Base):
    __tablename__ = "demo_rejected"
    __table_args__ = (
        Index("ix_demo_rejected_error_summary", "error_summary"),
        Index("ix_demo_rejected_primaryid", "primaryid"),
        Index("ix_demo_rejected_ingest_run", "ingest_run_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    primaryid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(64), nullable=False)
    source_line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingest_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.id"),
        nullable=False,
    )
    rejected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )