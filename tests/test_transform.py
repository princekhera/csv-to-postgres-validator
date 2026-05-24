"""Tests for the DemoRow → dict transform."""

from uuid import uuid4

from faers_validator.ingest.transform import to_demo_clean_dict
from faers_validator.models import DemoRow


def _valid_row(**overrides) -> DemoRow:
    base = {
        "primaryid": "1", "caseid": "1", "caseversion": "1",
        "i_f_code": "I", "rept_cod": "EXP", "mfr_sndr": "TEST",
        "e_sub": "Y", "reporter_country": "US",
    }
    return DemoRow.model_validate(base | overrides)


def test_minimal_row_produces_dict_with_all_required_keys():
    row = _valid_row()
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["primaryid"] == 1
    assert d["mfr_sndr"] == "TEST"
    assert d["age_years"] is None
    assert d["weight_kg"] is None


def test_full_date_produces_three_columns():
    row = _valid_row(event_dt="20240315")
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["event_dt"] == "20240315"
    assert d["event_dt_precision"] == "day"
    assert d["event_dt_value"].isoformat() == "2024-03-15"


def test_year_only_date_has_null_value_column():
    """Year-only dates can't be cast to a SQL DATE, so event_dt_value is None."""
    row = _valid_row(event_dt="2024")
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["event_dt"] == "2024"
    assert d["event_dt_precision"] == "year"
    assert d["event_dt_value"] is None


def test_age_normalisation_propagates_to_dict():
    row = _valid_row(age="50", age_cod="YR")
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["age"] == 50.0
    assert d["age_cod"] == "YR"
    assert d["age_years"] == 50.0


def test_weight_pounds_normalised_to_kg():
    row = _valid_row(wt="150", wt_cod="LBS")
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["wt"] == 150.0
    assert d["wt_cod"] == "LBS"
    assert 67.5 < d["weight_kg"] < 68.5


def test_enum_values_serialised_as_strings():
    """Database stores enum string values, not Python Enum objects."""
    row = _valid_row(sex="F", to_mfr="N")
    d = to_demo_clean_dict(row, ingest_run_id=uuid4())
    assert d["sex"] == "F"
    assert d["to_mfr"] == "N"
    assert isinstance(d["sex"], str)
