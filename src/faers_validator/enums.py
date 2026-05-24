"""Enum definitions for FAERS DEMO fields.

Each enum lists only values observed in the data or documented in the FAERS spec.
The validator rejects any value outside these sets.
"""

from enum import Enum


class InitialOrFollowup(str, Enum):
    """i_f_code: whether this is an initial report or a follow-up."""
    INITIAL = "I"
    FOLLOWUP = "F"


class Sex(str, Enum):
    """sex: patient sex. Spec mentions UNK/NS but 2026 Q1 data uses null instead."""
    FEMALE = "F"
    MALE = "M"


class AgeCode(str, Enum):
    """age_cod: unit of the age field."""
    DECADE = "DEC"
    YEAR = "YR"
    MONTH = "MON"
    WEEK = "WK"
    DAY = "DY"
    HOUR = "HR"


class AgeGroup(str, Enum):
    """age_grp: broad age category. Added in 2014Q3."""
    NEONATE = "N"      # < 1 month
    INFANT = "I"       # 1 month to 2 years
    CHILD = "C"        # 2 to 12 years
    ADOLESCENT = "T"   # 13 to 17 years
    ADULT = "A"        # 18 to 64 years
    ELDERLY = "E"      # 65+ years


class WeightCode(str, Enum):
    """wt_cod: unit of the weight field."""
    KILOGRAM = "KG"
    POUND = "LBS"


class ReportType(str, Enum):
    """rept_cod: type of report."""
    EXPEDITED = "EXP"
    PERIODIC = "PER"
    DIRECT = "DIR"
    DAY_30 = "30DAY"
    DAY_5 = "5DAY"


class ElectronicSubmission(str, Enum):
    """e_sub: was the report submitted electronically."""
    YES = "Y"
    NO = "N"


class ForwardedToManufacturer(str, Enum):
    """to_mfr: was the report forwarded to the manufacturer. 97% null in data."""
    YES = "Y"
    NO = "N"


# Conversion factors: multiply age × factor to get years
AGE_UNIT_TO_YEARS: dict[AgeCode, float] = {
    AgeCode.YEAR: 1.0,
    AgeCode.DECADE: 10.0,
    AgeCode.MONTH: 1 / 12,
    AgeCode.WEEK: 1 / 52,
    AgeCode.DAY: 1 / 365.25,
    AgeCode.HOUR: 1 / 8766,
}


# Conversion factors: multiply weight × factor to get kilograms
WEIGHT_UNIT_TO_KG: dict[WeightCode, float] = {
    WeightCode.KILOGRAM: 1.0,
    WeightCode.POUND: 0.453592,
}


# Age group bands — what years range corresponds to each age_grp code.
# Used for the cross-field consistency check (NOTES.md issue #12).
AGE_GROUP_BANDS: dict[AgeGroup, tuple[float, float]] = {
    AgeGroup.NEONATE: (0.0, 1 / 12),       # < 1 month
    AgeGroup.INFANT: (1 / 12, 2.0),        # 1 month to 2 years
    AgeGroup.CHILD: (2.0, 13.0),           # 2 to 12 years
    AgeGroup.ADOLESCENT: (13.0, 18.0),     # 13 to 17 years
    AgeGroup.ADULT: (18.0, 65.0),          # 18 to 64 years
    AgeGroup.ELDERLY: (65.0, 150.0),       # 65+
}

# Bands that catch only the catastrophic mismatches (e.g. DEC↔YR miscoding).
# A row outside these wider bounds is genuinely wrong, not a boundary disagreement.
AGE_GROUP_BANDS_IMPLAUSIBLE: dict[AgeGroup, tuple[float, float]] = {
    AgeGroup.NEONATE: (0.0, 1.0),
    AgeGroup.INFANT: (0.0, 5.0),
    AgeGroup.CHILD: (0.0, 18.0),
    AgeGroup.ADOLESCENT: (5.0, 25.0),
    AgeGroup.ADULT: (10.0, 80.0),
    AgeGroup.ELDERLY: (40.0, 150.0),
}
