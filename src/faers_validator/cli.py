"""Command-line interface for the FAERS validator."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from .db.engine import make_engine
from .ingest.pipeline import ingest_demo_file

app = typer.Typer(
    help="FAERS data validator and Postgres ingester.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """FAERS validator: validates and loads FDA adverse event data into Postgres."""
@app.command()
def ingest(
    csv: Path = typer.Option(..., exists=True, dir_okay=False, help="Path to DEMO CSV file"),
    quarter: str = typer.Option(..., help="Quarter label, e.g. 2026Q1"),
    batch_size: int = typer.Option(5000, help="Rows per batch insert"),
    log_level: str = typer.Option("INFO", help="Logging level"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Validate every row but write nothing to the database",
    ),
    upsert: bool = typer.Option(
        False, "--upsert",
        help="Replace existing rows with the same primaryid (idempotent re-ingest)",
    ),
) -> None:
    """Ingest a FAERS DEMO file into Postgres."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    engine = make_engine()
    result = ingest_demo_file(
        engine, csv, quarter,
        batch_size=batch_size, dry_run=dry_run, upsert=upsert,
    )

    if dry_run:
        typer.echo(
            f"Dry run: seen={result['rows_seen']:,} "
            f"clean={result['rows_clean']:,} rejected={result['rows_rejected']:,}"
        )
        if result["rejection_reasons"]:
            for reason, count in result["rejection_reasons"].items():
                typer.echo(f"  {reason}: {count}")
    else:
        typer.echo(
            f"Ingest {result['run_id']}: seen={result['rows_seen']:,} "
            f"clean={result['rows_clean']:,} rejected={result['rows_rejected']:,}"
        )

def main() -> None:
    app()


if __name__ == "__main__":
    main()
