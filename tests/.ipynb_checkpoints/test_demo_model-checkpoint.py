"""Tests for the DemoRow model.

Every test corresponds to a finding in NOTES.md. Each issue gets both a
'should accept' and 'should reject' case where applicable.
"""

import pytest
from pydantic import ValidationError

from faers_validator.models import DemoRow
from faers_validator.partial_date import DatePrecision


# ── Reusable fixture for a minimal valid row ─────────────────────────

@pytest.fixture
def minimal_row() -> dict:
    """The smallest dict that produces a valid DemoRow."""
    return {
        "primaryid": "1234567",
        "caseid": "12345",
        "caseversion": "1",
        "i_f_code": "I",
        "rept_cod": "EXP",
        "mfr_sndr": "PFIZER",
        "e_sub": "Y",
        "reporter_country": "US",
    }


def test_minimal_valid_row(minimal_row):
    row = DemoRow.model_validate(minimal_row)
    assert row.primaryid == 1234567
    assert row.age_years is None
    assert row.weight_kg is None


# ── Issue #1: to_mfr enum ────────────────────────────────────────────

def test_to_mfr_accepts_Y_N_and_null(minimal_row):
    DemoRow.model_validate({**minimal_row, "to_mfr": "Y"})
    DemoRow.model_validate({**minimal_row, "to_mfr": "N"})
    DemoRow.model_validate(minimal_row)  # null


def test_to_mfr_rejects_other(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "to_mfr": "X"})


# ── Issue #2: i_f_code enum ──────────────────────────────────────────

def test_i_f_code_rejects_other(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "i_f_code": "Z"})


# ── Issue #3: partial dates ──────────────────────────────────────────

def test_partial_date_year_only(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "event_dt": "2024"})
    assert row.event_dt.precision == DatePrecision.YEAR
    assert row.event_dt.year == 2024
    assert row.event_dt.month is None


def test_partial_date_year_month(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "event_dt": "202403"})
    assert row.event_dt.precision == DatePrecision.MONTH
    assert row.event_dt.month == 3


def test_partial_date_full(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "event_dt": "20240315"})
    assert row.event_dt.precision == DatePrecision.DAY
    assert row.event_dt.day == 15


def test_partial_date_invalid_day_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "event_dt": "20240230"})  # Feb 30


def test_partial_date_invalid_length_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "event_dt": "202"})


# ── Issue #5: age/age_cod consistency ───────────────────────────────

def test_age_without_age_cod_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "age": "50"})


def test_age_cod_without_age_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "age_cod": "YR"})


def test_age_normalisation_years(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "age": "50", "age_cod": "YR"})
    assert row.age_years == 50.0


def test_age_normalisation_days(minimal_row):
    row = DemoRow.model_validate(
        {**minimal_row, "age": "10950", "age_cod": "DY"}
    )
    assert 29.9 < row.age_years < 30.1


# ── Issue #6: weight/wt_cod consistency and normalisation ───────────

def test_weight_without_wt_cod_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({**minimal_row, "wt": "70"})


def test_weight_pounds_normalised(minimal_row):
    row = DemoRow.model_validate(
        {**minimal_row, "wt": "150", "wt_cod": "LBS"}
    )
    assert 67.5 < row.weight_kg < 68.5


# ── Issue #8: country sentinels ─────────────────────────────────────

def test_country_not_specified_coerced_to_none(minimal_row):
    row = DemoRow.model_validate(
        {**minimal_row, "reporter_country": "COUNTRY NOT SPECIFIED"}
    )
    assert row.reporter_country is None


# ── Issue #10: suspect imputed event date ───────────────────────────

def test_event_dt_first_of_year_flagged(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "event_dt": "20240101"})
    assert row.event_dt_suspect_imputed is True


def test_event_dt_normal_day_not_flagged(minimal_row):
    row = DemoRow.model_validate({**minimal_row, "event_dt": "20240315"})
    assert row.event_dt_suspect_imputed is False


# ── Issue #12: cross-field age miscoding ────────────────────────────

def test_dec_yr_miscoding_rejected(minimal_row):
    """The canonical case: age=23, age_cod=DEC, age_grp=A (Adult).
    A 230-year-old cannot be an Adult. This is the cross-field check
    that single-column validation misses.
    """
    with pytest.raises(ValidationError) as exc:
        DemoRow.model_validate({
            **minimal_row,
            "age": "23",
            "age_cod": "DEC",
            "age_grp": "A",
        })
    assert "age_grp" in str(exc.value)


def test_age_implausibly_high_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({
            **minimal_row,
            "age": "200",
            "age_cod": "YR",
        })


def test_weight_implausibly_high_rejected(minimal_row):
    with pytest.raises(ValidationError):
        DemoRow.model_validate({
            **minimal_row,
            "wt": "5000",
            "wt_cod": "KG",
        })


def test_valid_elderly_row(minimal_row):
    """Sanity: a normal elderly patient should pass everything."""
    row = DemoRow.model_validate({
        **minimal_row,
        "age": "75",
        "age_cod": "YR",
        "age_grp": "E",
        "sex": "F",
        "wt": "65",
        "wt_cod": "KG",
        "event_dt": "20240615",
    })
    assert row.age_years == 75.0
    assert row.weight_kg == 65.0
    assert row.event_dt_suspect_imputed is False