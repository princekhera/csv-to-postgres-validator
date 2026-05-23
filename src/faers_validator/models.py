"""Pydantic model for one row of the FAERS DEMO file.

Each field's type and each @model_validator corresponds to a finding
documented in NOTES.md. The model is the executable form of the data
contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import (
    AGE_GROUP_BANDS,
    AGE_GROUP_BANDS_IMPLAUSIBLE,
    AGE_UNIT_TO_YEARS,
    WEIGHT_UNIT_TO_KG,
    AgeCode,
    AgeGroup,
    ElectronicSubmission,
    ForwardedToManufacturer,
    InitialOrFollowup,
    ReportType,
    Sex,
    WeightCode,
)
from .partial_date import PartialDate

# Sentinel values seen in country fields that are logically null.
COUNTRY_NULL_SENTINELS = {"COUNTRY NOT SPECIFIED"}


def _coerce_optional_str(v: Any) -> str | None:
    """FAERS distinguishes empty string and missing inconsistently. Treat both as None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_partial_date(v: Any) -> PartialDate | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return PartialDate.parse(s)


class DemoRow(BaseModel):
    """One row of DEMO data, fully validated and typed."""

    # Identifiers (NOTES.md: confirmed-from-spec, required, unique)
    primaryid: int = Field(..., description="Unique row identifier")
    caseid: int = Field(..., description="Case identifier; not unique across versions")
    caseversion: int = Field(..., ge=1, description="Case version number, 1-indexed")

    # Initial/followup flag (issue #2)
    i_f_code: InitialOrFollowup

    # Dates (issue #3, #4, #10)
    event_dt: PartialDate | None = None
    mfr_dt: PartialDate | None = None
    init_fda_dt: PartialDate | None = None
    fda_dt: PartialDate | None = None
    rept_dt: PartialDate | None = None

    rept_cod: ReportType

    # Free-text optional fields
    auth_num: str | None = None
    mfr_num: str | None = None
    mfr_sndr: str  # always present in the data, no nulls observed
    lit_ref: str | None = None  # issue #11: free text, accept as-is

    # Age (issue #5, #12)
    age: float | None = None
    age_cod: AgeCode | None = None
    age_grp: AgeGroup | None = None
    age_years: float | None = None  # derived

    # Sex (issue #7)
    sex: Sex | None = None

    e_sub: ElectronicSubmission

    # Weight (issue #6, #12)
    wt: float | None = None
    wt_cod: WeightCode | None = None
    weight_kg: float | None = None  # derived

    # Forwarded-to-mfr flag (issue #1)
    to_mfr: ForwardedToManufacturer | None = None

    # Reporter occupation
    occp_cod: str | None = None

    # Geography (issue #8, #9)
    reporter_country: str | None = None  # sentinel "COUNTRY NOT SPECIFIED" coerces to None (issue #8)
    
    occr_country: str | None = None

    # Annotations / soft warnings — populated during validation, not from input
    event_dt_suspect_imputed: bool = False  # issue #10
    age_group_boundary_mismatch: bool = False  # issue #12, soft


    # ── String preprocessing ─────────────────────────────────────────

    @field_validator(
        "auth_num", "mfr_num", "lit_ref", "occp_cod", "occr_country",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        return _coerce_optional_str(v)

    @field_validator("reporter_country", "occr_country", mode="before")
    @classmethod
    def _country_sentinels_to_none(cls, v: Any) -> Any:
        """Coerce 'COUNTRY NOT SPECIFIED' to None (issue #8)."""
        s = _coerce_optional_str(v)
        if s in COUNTRY_NULL_SENTINELS:
            return None
        return s


    # reporter_country: the spec implies always-present, and the raw data
    # confirms zero true nulls. However, ~1% of rows use "COUNTRY NOT SPECIFIED"
    # as a sentinel meaning "unknown reporter country." We coerce that sentinel
    # to None on ingest so downstream consumers see standard SQL NULL semantics
    # for "unknown," rather than a magic string. Documented as issue #8.
    
    # ── Date parsing ─────────────────────────────────────────────────

    @field_validator(
        "event_dt", "mfr_dt", "init_fda_dt", "fda_dt", "rept_dt",
        mode="before",
    )
    @classmethod
    def _parse_dates(cls, v: Any) -> Any:
        return _parse_partial_date(v)

    # ── Numeric parsing ──────────────────────────────────────────────

    @field_validator("age", "wt", mode="before")
    @classmethod
    def _empty_numeric_to_none(cls, v: Any) -> Any:
        if v is None or v == "":
            return None
        return v

    # ── Cross-field rules (model_validator runs after fields are set) ─

    @model_validator(mode="after")
    def _check_age_unit_consistency(self) -> DemoRow:
        """Issue #5: age and age_cod must be both-or-neither."""
        if (self.age is None) != (self.age_cod is None):
            raise ValueError(
                f"age and age_cod must be both populated or both null "
                f"(got age={self.age}, age_cod={self.age_cod})"
            )
        return self

    @model_validator(mode="after")
    def _derive_age_years(self) -> DemoRow:
        if self.age is not None and self.age_cod is not None:
            factor = AGE_UNIT_TO_YEARS[self.age_cod]
            self.age_years = round(self.age * factor, 4)
        return self

    @model_validator(mode="after")
    def _check_age_implausible(self) -> DemoRow:
        """Issue #12: reject ages over 150 years equivalent."""
        if self.age_years is not None and self.age_years > 150:
            raise ValueError(
                f"age_years {self.age_years} exceeds 150 (raw: age={self.age}, "
                f"age_cod={self.age_cod})"
            )
        return self

    @model_validator(mode="after")
    def _check_age_group_consistency(self) -> "DemoRow":
        """Issue #12: graded check.

        - Reject if age_years falls outside the *implausible* band — this catches
          the DEC↔YR miscoding (e.g. age=23, age_cod=DEC, age_grp=A normalises to
          230 years, which is outside even the generous Adult bounds of 10–80).
        - Annotate if age_years is outside the *strict* band but inside the
          implausible band — these are boundary disagreements (e.g. age=12,
          age_grp=T) and the row is preserved.
        """
        if self.age_years is None or self.age_grp is None:
            return self

        strict_low, strict_high = AGE_GROUP_BANDS[self.age_grp]
        impl_low, impl_high = AGE_GROUP_BANDS_IMPLAUSIBLE[self.age_grp]

        if not (impl_low <= self.age_years <= impl_high):
            raise ValueError(
                f"age_years {self.age_years} is implausible for age_grp "
                f"{self.age_grp.value} (implausible range: {impl_low}–{impl_high})"
            )

        if not (strict_low <= self.age_years < strict_high):
            self.age_group_boundary_mismatch = True

        return self

    @model_validator(mode="after")
    def _check_weight_unit_consistency(self) -> DemoRow:
        """Issue #6: wt and wt_cod must be both-or-neither."""
        if (self.wt is None) != (self.wt_cod is None):
            raise ValueError(
                f"wt and wt_cod must be both populated or both null "
                f"(got wt={self.wt}, wt_cod={self.wt_cod})"
            )
        return self

    @model_validator(mode="after")
    def _derive_weight_kg(self) -> DemoRow:
        if self.wt is not None and self.wt_cod is not None:
            factor = WEIGHT_UNIT_TO_KG[self.wt_cod]
            self.weight_kg = round(self.wt * factor, 4)
        return self

    @model_validator(mode="after")
    def _check_weight_implausible(self) -> DemoRow:
        """Issue #12: reject weights over 1000kg or below 0."""
        if self.weight_kg is not None and not (0 < self.weight_kg <= 1000):
            raise ValueError(
                f"weight_kg {self.weight_kg} out of plausible range (0, 1000] "
                f"(raw: wt={self.wt}, wt_cod={self.wt_cod})"
            )
        return self

    @model_validator(mode="after")
    def _flag_suspect_imputed_dates(self) -> DemoRow:
        """Issue #10: flag event_dt values that look like 0101 / MM01 imputations."""
        if self.event_dt is not None and self.event_dt.is_first_of_period():
            self.event_dt_suspect_imputed = True
        return self
    

