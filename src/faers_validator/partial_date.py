"""PartialDate type for FAERS date fields.

FAERS preserves the granularity submitted by reporters: a date may be a full
YYYYMMDD, a year-month YYYYMM, or a year YYYY alone (NOTES.md issue #3).
We do not coerce to datetime.date because that would invent precision the
data does not contain.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel


class DatePrecision(str, Enum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class PartialDate(BaseModel):
    """A date with explicit precision.

    `raw` keeps the original string for provenance.
    `precision` indicates what was actually submitted.
    `year`, `month`, `day` are populated as available.
    """
    raw: str
    precision: DatePrecision
    year: int
    month: int | None = None
    day: int | None = None

    @classmethod
    def parse(cls, value: str | None) -> PartialDate | None:
        if value is None or value == "":
            return None
        s = str(value).strip()
        if len(s) == 4:
            return cls(raw=s, precision=DatePrecision.YEAR, year=int(s))
        if len(s) == 6:
            year, month = int(s[:4]), int(s[4:6])
            if not 1 <= month <= 12:
                raise ValueError(f"invalid month in partial date: {s!r}")
            return cls(raw=s, precision=DatePrecision.MONTH, year=year, month=month)
        if len(s) == 8:
            year, month, day = int(s[:4]), int(s[4:6]), int(s[6:8])
            # Use datetime.date for day validation — catches Feb 30, etc.
            date(year, month, day)
            return cls(
                raw=s, precision=DatePrecision.DAY, year=year, month=month, day=day,
            )
        raise ValueError(
            f"partial date must be 4, 6, or 8 digits; got {s!r} (length {len(s)})"
        )

    def is_first_of_period(self) -> bool:
        """True if a full date ends in MM01 or 0101 (NOTES.md issue #10)."""
        if self.precision != DatePrecision.DAY:
            return False
        return self.day == 1


def _validate_partial_date(value: Any) -> PartialDate | None:
    if value is None or value == "":
        return None
    if isinstance(value, PartialDate):
        return value
    return PartialDate.parse(value)

