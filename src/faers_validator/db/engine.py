"""Database engine and session factory.

The engine is configured once per process; sessions are short-lived
units of work created from the engine. The connection URL is read
from the DATABASE_URL environment variable so the same code works
locally, in CI, and in production.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

DEFAULT_LOCAL_URL = "postgresql+psycopg://dev:dev@localhost:5432/validator"


def get_database_url() -> str:
    """Return the database URL, falling back to the local Docker default."""
    return os.environ.get("DATABASE_URL", DEFAULT_LOCAL_URL)


def make_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    `insertmanyvalues_page_size` controls how many rows are batched into
    a single multi-row INSERT statement when using `execute(insert(...), [dicts])`.
    The default is 1000; tuning depends on row size and network latency.
    """
    return create_engine(
        url or get_database_url(),
        pool_pre_ping=True,
        future=True,
        insertmanyvalues_page_size=1000,
    )

# Module-level engine and session factory — created lazily by the CLI.
# Not instantiated at import time, so tests can substitute their own.
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
