"""Shared pytest fixtures for the FAERS validator tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from testcontainers.postgres import PostgresContainer

from faers_validator.db.engine import make_engine
from faers_validator.db.tables import Base


@pytest.fixture(scope="session")
def postgres_container():
    """Start a throwaway Postgres container for the whole test session."""
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="session")
def engine(postgres_container) -> Engine:
    """SQLAlchemy engine pointing at the test container."""
    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+psycopg"
    )
    return make_engine(url)


@pytest.fixture(scope="session", autouse=True)
def _create_schema_once(engine: Engine):
    """Create the faers schema and tables once for the whole session."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS faers"))
    Base.metadata.create_all(engine)
    yield
    # Cleanup is automatic when the container terminates


@pytest.fixture
def clean_db(engine: Engine):
    """Truncate all tables before each test so tests are independent."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE faers.demo_clean, faers.demo_rejected, faers.ingest_run CASCADE"
        ))
    yield engine


@pytest.fixture
def tiny_csv() -> Path:
    """Path to the 5-row fixture CSV."""
    return Path(__file__).parent / "fixtures" / "demo_tiny.txt"
