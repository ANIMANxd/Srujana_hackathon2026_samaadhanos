"""v5 insights maths.

Pure functions only: no I/O, no clock, no randomness. The customer book's
identity rules live in `backend.insights.identity`; persistence and wiring live
in `backend.store.customers`.
"""

from backend.insights.identity import (
    ATTACH_SUGGESTION,
    DEFAULT_NAME_MATCH_THRESHOLD,
    GSTIN_PATTERN,
    LINK_AS_GROUP_SUGGESTION,
    PAN_KIND,
    PROVISIONAL_KIND,
    CustomerRecord,
    GstinCheck,
    Resolution,
    Suggestion,
    normalize_name,
    pan_from_gstin,
    resolve,
    suggestions,
    validate_gstin,
)

__all__ = [
    "ATTACH_SUGGESTION",
    "DEFAULT_NAME_MATCH_THRESHOLD",
    "GSTIN_PATTERN",
    "LINK_AS_GROUP_SUGGESTION",
    "PAN_KIND",
    "PROVISIONAL_KIND",
    "CustomerRecord",
    "GstinCheck",
    "Resolution",
    "Suggestion",
    "normalize_name",
    "pan_from_gstin",
    "resolve",
    "suggestions",
    "validate_gstin",
]
