"""Map Pydantic validation errors to a short, queryable category string.

The `demo_rejected.error_summary` column is indexed and used for
operational queries like "how many rows were rejected for weight issues
this quarter". A free-text error message wouldn't aggregate well; this
mapping produces a small enumerable set of categories.
"""

from __future__ import annotations

from typing import Any

# Substring → category. First match wins. Order matters: more specific
# patterns above more general ones.
_PATTERNS: list[tuple[str, str]] = [
    ("inconsistent with age_grp", "age_group_inconsistent"),
    ("implausible for age_grp", "age_group_inconsistent"),
    ("age_years", "age_implausible"),
    ("age and age_cod must be both", "age_unit_mismatch"),
    ("weight_kg", "weight_implausible"),
    ("wt and wt_cod must be both", "weight_unit_mismatch"),
    ("partial date", "date_invalid"),
    ("Input should be", "type_invalid"),
    ("Field required", "field_missing"),
]


def summarise(errors: list[dict[str, Any]]) -> str:
    """Reduce a list of Pydantic error dicts to a single category string.

    If multiple errors fire, the first matching category wins. Unknown
    errors land in `other` so they're still queryable.
    """
    for err in errors:
        msg = err.get("msg", "")
        for pattern, category in _PATTERNS:
            if pattern in msg:
                return category
    return "other"
