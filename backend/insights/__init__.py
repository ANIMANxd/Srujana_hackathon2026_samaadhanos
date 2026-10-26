"""v5 insights maths.

Pure functions only: no I/O, no clock, no randomness. The customer book's
identity rules live in `backend.insights.identity`, per-customer payment
statistics in `backend.insights.stats`, and portfolio views in
`backend.insights.insights`; persistence and wiring live in
`backend.store.customers`.
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
from backend.insights.insights import (
    BEFORE_MARCH_NOTE,
    CASH_IN_LABEL,
    BeforeMarchItem,
    CashInWeek,
    ConcentrationResult,
    ConcentrationShare,
    PortfolioInsightsResult,
    TermsFlag,
    portfolio_insights,
)
from backend.insights.stats import (
    NOT_ENOUGH_HISTORY,
    STATUS_NO_DUE_DATE,
    STATUS_NOT_DUE,
    STATUS_OVERDUE,
    STATUS_PAID,
    CaseSnapshot,
    CustomerStatsResult,
    InsightsConfig,
    InvoiceSeriesPoint,
    PaymentRecord,
    TrackSummary,
    customer_stats,
    q2,
)

__all__ = [
    "ATTACH_SUGGESTION",
    "BEFORE_MARCH_NOTE",
    "CASH_IN_LABEL",
    "DEFAULT_NAME_MATCH_THRESHOLD",
    "GSTIN_PATTERN",
    "LINK_AS_GROUP_SUGGESTION",
    "NOT_ENOUGH_HISTORY",
    "PAN_KIND",
    "PROVISIONAL_KIND",
    "STATUS_NO_DUE_DATE",
    "STATUS_NOT_DUE",
    "STATUS_OVERDUE",
    "STATUS_PAID",
    "BeforeMarchItem",
    "CashInWeek",
    "CaseSnapshot",
    "ConcentrationResult",
    "ConcentrationShare",
    "CustomerRecord",
    "CustomerStatsResult",
    "GstinCheck",
    "InsightsConfig",
    "InvoiceSeriesPoint",
    "PaymentRecord",
    "PortfolioInsightsResult",
    "Resolution",
    "Suggestion",
    "TermsFlag",
    "TrackSummary",
    "customer_stats",
    "normalize_name",
    "pan_from_gstin",
    "portfolio_insights",
    "q2",
    "resolve",
    "suggestions",
    "validate_gstin",
]
