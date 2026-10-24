"""A fixed, valid sample CaseEvaluationResponse for the contract-v1 scaffold.

This is NOT the engine. It returns hand-set placeholder constants so the
frontend has something schema-valid to render in every block while the engine
is built. It computes nothing: no dates are stepped, no interest is accrued,
no rule is evaluated, no number below is derived from another. Every value is
a fixed, obviously-synthetic constant, and the whole response is flagged with
a PLACEHOLDER_DATA warning plus a PLACEHOLDER assumption (golden rule 7:
mock values must be visibly labelled "placeholder" until replaced by engine
output). Replace this module wholesale with a call to engine.evaluate once
the engine lands; do not "improve" these numbers.
"""

from datetime import date
from decimal import Decimal

from backend.app.schemas import (
    AppropriationMode,
    BuyerCost,
    Citation,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    Deferral,
    DeferralInputs,
    Defense,
    DefenseStatus,
    DisclosureFlag,
    EvidenceReadiness,
    Financials,
    Jurisdiction,
    JurisdictionCheck,
    JurisdictionStatus,
    LedgerKind,
    LedgerRow,
    Limitation,
    LimitationStatus,
    ObjectionStatus,
    PermanentLoss,
    PaymentBoundaryConvention,
    RateMode,
    RateSegment,
    ReadinessBand,
    ReadinessReason,
    Timeline,
    Warning,
    WarningSeverity,
)

D = Decimal

PLACEHOLDER_WARNING = Warning(
    code="PLACEHOLDER_DATA",
    severity=WarningSeverity.WARN,
    text=(
        "This response is a fixed placeholder from the contract scaffold, not the "
        "engine. Every number, date and status below is a hand-set synthetic sample "
        "and must not be relied on. It will be replaced by engine output."
    ),
)


def placeholder_evaluation(request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Return a fixed sample response. Only case_id and calculation_date echo
    the request (neither is legal math); everything else is a constant."""
    return CaseEvaluationResponse(
        case_id=request.case_id,
        calculation_date=request.transaction.calculation_date,
        jurisdiction=Jurisdiction(
            status=JurisdictionStatus.INSUFFICIENT_DATA,
            eligible=False,
            checks=[
                JurisdictionCheck(
                    id="enterprise_class",
                    passed=None,
                    detail="PLACEHOLDER: the engine has not run, so no check has passed.",
                    rule_ref="gate.enterprise_class",
                ),
                JurisdictionCheck(
                    id="silpi_chronology",
                    passed=None,
                    detail="PLACEHOLDER: the engine has not run, so no check has passed.",
                    rule_ref="gate.silpi_chronology",
                ),
            ],
            alternative_remedy=None,
        ),
        timeline=Timeline(
            delivery_date=date(2026, 1, 10),
            objection_window_end=date(2026, 1, 25),
            objection_status=ObjectionStatus.DEEMED_ACCEPTANCE,
            acceptance_date=date(2026, 1, 10),
            agreed_days=30,
            applied_days=30,
            clamped=False,
            due_date=date(2026, 2, 9),
            appointed_day=date(2026, 2, 10),
            days_overdue=40,
            late_complaints=[],
        ),
        financials=Financials(
            rate_mode=RateMode.FLOATING,
            appropriation_mode=AppropriationMode.INTEREST_FIRST,
            payment_boundary_convention=PaymentBoundaryConvention.PAYMENT_DATE_IS_REST_BOUNDARY,
            rate_segments=[
                RateSegment(
                    from_=date(2026, 2, 10),
                    to=date(2026, 3, 21),
                    bank_rate_pct=D("5.50"),
                    statutory_rate_pct=D("16.50"),
                )
            ],
            ledger=[
                LedgerRow(
                    kind=LedgerKind.STUB,
                    from_=date(2026, 2, 10),
                    to=date(2026, 3, 21),
                    opening=D("100000.00"),
                    interest=D("1471.23"),
                    payment=D("0.00"),
                    closing=D("101471.23"),
                    rate_pct=D("16.50"),
                    note="PLACEHOLDER row, not engine output.",
                )
            ],
            interest_total=D("1471.23"),
            principal_outstanding=D("100000.00"),
            interest_outstanding=D("1471.23"),
            total_claim=D("101471.23"),
            daily_accrual=D("45.29"),
        ),
        buyer_cost=BuyerCost(
            permanent_loss=PermanentLoss(
                interest_non_deductible=D("1471.23"),
                pretax_equivalent_rate_pct=D("23.98"),
            ),
            deferral=Deferral(
                applies=False,
                checkpoints=[],
                deferral_cost=None,
                inputs=DeferralInputs(
                    cost_of_capital_pct=request.buyer.cost_of_capital_pct,
                    years_deferred=D("1.00"),
                ),
            ),
            disclosure_flags=[
                DisclosureFlag(
                    id="s22_disclosure",
                    text="PLACEHOLDER: s.22 audited-accounts disclosure flag.",
                    verified=False,
                )
            ],
            other_pressure_points=[],
        ),
        limitation=Limitation(
            expiry=None,  # PLACEHOLDER: limitation_years is still an open question (OQ-6).
            status=LimitationStatus.UNKNOWN,
            events=[],
        ),
        defenses=[
            Defense(
                id="placeholder_defense",
                buyer_says="PLACEHOLDER: a sample buyer argument.",
                rule_ref="defenses.placeholder",
                status=DefenseStatus.OPEN_QUESTION,
                evidence_have=[],
                evidence_missing=[],
            )
        ],
        evidence_readiness=EvidenceReadiness(
            score=40,
            band=ReadinessBand.ACTION_NEEDED,
            reasons=[
                ReadinessReason(
                    code="PLACEHOLDER",
                    delta=0,
                    text="PLACEHOLDER: the engine has not scored this case.",
                )
            ],
            missing=[],
            blocked_stages=[4],
            recommended_stage=1,
        ),
        citations=[
            Citation(
                id="placeholder_citation",
                rule="PLACEHOLDER: no rule has been applied.",
                statute_ref="none",
                config_key=None,
                verified=False,
            )
        ],
        assumptions=[
            "PLACEHOLDER: this entire response is synthetic sample data from the "
            "contract scaffold, not engine output. No number here is legal advice."
        ],
        warnings=[PLACEHOLDER_WARNING],
    )
