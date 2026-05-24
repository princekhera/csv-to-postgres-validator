"""Chunked CSV reader for FAERS pipe-delimited files.

FAERS files can be hundreds of MB. Reading them whole into memory works
on small quarters but doesn't scale. This module wraps pandas with the
exact read options needed for FAERS and yields records one at a time
while reading in chunks under the hood.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_CHUNK_SIZE = 10_000


def iter_demo_records(
    path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield (line_number, record_dict) for each row of a FAERS DEMO file.

    Read options are derived from NOTES.md exploration:
    - Latin-1 encoding (not UTF-8)
    - '$' delimiter
    - All columns as strings; validation does the typing
    - Empty strings treated as nulls
    """
    line_number = 1  # header is line 1, first data row is line 2
    chunk_iter = pd.read_csv(
        path,
        sep="$",
        encoding="latin-1",
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        on_bad_lines="warn",
        chunksize=chunk_size,
    )
    for chunk in chunk_iter:
        for record in chunk.to_dict(orient="records"):
            line_number += 1
            cleaned = {k: (None if pd.isna(v) else v) for k, v in record.items()}
            yield line_number, cleaned