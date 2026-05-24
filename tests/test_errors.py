"""Tests for the validation-error-summary mapping."""

from faers_validator.ingest.errors import summarise


def test_age_implausible_summary():
    errors = [{"type": "value_error", "loc": ["age_years"],
               "msg": "Value error, age_years 200.0 exceeds 150"}]
    assert summarise(errors) == "age_implausible"


def test_age_group_inconsistent_summary():
    errors = [{"type": "value_error", "loc": [],
               "msg": "Value error, age_years 230.0 is implausible for age_grp A"}]
    assert summarise(errors) == "age_group_inconsistent"


def test_age_unit_mismatch_summary():
    errors = [{"type": "value_error", "loc": [],
               "msg": "Value error, age and age_cod must be both populated or both null"}]
    assert summarise(errors) == "age_unit_mismatch"


def test_weight_implausible_summary():
    errors = [{"type": "value_error", "loc": ["weight_kg"],
               "msg": "Value error, weight_kg 0.0 out of plausible range"}]
    assert summarise(errors) == "weight_implausible"


def test_unknown_error_categorised_as_other():
    errors = [{"type": "some_new_error", "loc": ["weird_field"],
               "msg": "something we have never seen before"}]
    assert summarise(errors) == "other"


def test_first_match_wins_when_multiple_errors():
    """If a row has multiple errors, the first matching category is returned."""
    errors = [
        {"type": "value_error", "loc": [], "msg": "Value error, weight_kg 0.0 out of plausible range"},
        {"type": "value_error", "loc": [], "msg": "Value error, age_years 200 exceeds 150"},
    ]
    # weight pattern appears in the list before age, so weight wins
    assert summarise(errors) == "weight_implausible"