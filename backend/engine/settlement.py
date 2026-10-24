"""settlement.py — plain settlement arithmetic (architecture.md section 8.1).

Takes the figures an evaluation already produced and answers one question: if
the buyer pays `upfront_pct` now, the supplier waives `waiver_pct` of the
outstanding interest, and the rest arrives `days_to_second_payment` days later,
what does the supplier actually end up with?

**Arithmetic only.** No rate, no date stepping, no statutory rule is applied
here, so this module reads no config and emits no citations: every figure in the
offer comes from the evaluation and from the negotiator's inputs. What it does
emit is the list of assumptions behind the numbers, because which lever applies
to what is a choice the two sides should see stated.

Not part of the frozen contract: section 8.1 names `POST /simulate-settlement`
but section 8.3 defines no response schema for it, so `SettlementResult` is an
engine-local shape until the API agent adds one (additive-only, section 9).

The three buyer-cost lines are never touched here either: a settlement splits
principal and interest, it does not combine permanent loss, deferral and
disclosure into anything (golden rule 8).
"""

from dataclasses import dataclass
from decimal import Decimal

from backend.engine.money import as_percent, parse_money, rupees

# Payment slots in the offer, ordered as cash arrives.
PAYMENT_UPFRONT = "UPFRONT"
PAYMENT_SECOND = "SECOND"

# Side of the deal each lever is described from.
ASSUMPTION_WAIVER_ON_INTEREST = (
    "waiver_pct applies to outstanding interest only; principal is recovered in full, "
    "so the waiver never writes off what the buyer actually owes for the goods."
)
ASSUMPTION_UPFRONT_ON_PAYABLE = (
    "upfront_pct is applied to the amount payable after the waiver, not to the "
    "original claim, so the two payments always add up to what the buyer must pay."
)
ASSUMPTION_NO_DISCOUNTING = (
    "No time value of money is applied: days_to_second_payment says when the second "
    "payment lands but does not reduce net_recovery. The figures are nominal rupees."
)
ASSUMPTION_ROUNDING = (
    "Amounts round half-up to 0.01. The upfront payment is rounded and the second "
    "takes the exact remainder, so the payments sum to the payable without a paisa "
    "leaking."
)


class SettlementInputError(ValueError):
    """A settlement input is out of range. Plain English, no clamping."""


@dataclass(frozen=True)
class SettlementPayment:
    """One payment in the offer, timed in days from now rather than by date."""

    kind: str  # UPFRONT | SECOND
    days_from_now: int
    amount: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "days_from_now": self.days_from_now,
            "amount": self.amount,
        }


@dataclass(frozen=True)
class SettlementResult:
    """The split offer, with the supplier's net position stated plainly.

    There is deliberately no field adding the buyer-cost lines to these figures
    (golden rule 8).
    """

    total_claim: Decimal
    interest_waived: Decimal
    interest_paid: Decimal
    principal_paid: Decimal
    total_payable: Decimal
    payments: list[SettlementPayment]
    net_recovery: Decimal
    upfront_pct: Decimal
    waiver_pct: Decimal
    days_to_second_payment: int
    assumptions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "total_claim": self.total_claim,
            "interest_waived": self.interest_waived,
            "interest_paid": self.interest_paid,
            "principal_paid": self.principal_paid,
            "total_payable": self.total_payable,
            "payments": [p.to_dict() for p in self.payments],
            "net_recovery": self.net_recovery,
            "upfront_pct": self.upfront_pct,
            "waiver_pct": self.waiver_pct,
            "days_to_second_payment": self.days_to_second_payment,
            "assumptions": list(self.assumptions),
        }


def _percent(value, *, name: str) -> Decimal:
    """A 0-100 percentage. Out of range is refused rather than clamped."""
    pct = parse_money(value)
    if pct < 0 or pct > 100:
        raise SettlementInputError(f"{name} must be between 0 and 100, not {pct}")
    return pct


def evaluate_settlement(
    *,
    principal_outstanding,
    interest_outstanding,
    upfront_pct,
    waiver_pct,
    days_to_second_payment: int,
) -> SettlementResult:
    """Split a settlement offer (section 8.1, `/simulate-settlement`).

    `principal_outstanding` and `interest_outstanding` come from the evaluation's
    `financials`; the three remaining inputs are what the negotiator is proposing.
    Every amount is Decimal — floats are rejected, so no rounding error reaches
    an offer figure.
    """
    principal = parse_money(principal_outstanding)
    interest = parse_money(interest_outstanding)
    if principal < 0:
        raise SettlementInputError(f"principal_outstanding cannot be negative, not {principal}")
    if interest < 0:
        raise SettlementInputError(f"interest_outstanding cannot be negative, not {interest}")

    upfront = _percent(upfront_pct, name="upfront_pct")
    waiver = _percent(waiver_pct, name="waiver_pct")

    # Whole days only: int(30.5) would silently become 30 and misstate when the
    # second payment lands, so the fraction is refused rather than floored.
    try:
        days_value = Decimal(str(days_to_second_payment))
    except Exception as exc:  # noqa: BLE001 - Decimal raises several types
        raise SettlementInputError(
            f"days_to_second_payment must be a whole number of days, not "
            f"{days_to_second_payment!r}"
        ) from exc
    if not days_value.is_finite() or days_value != days_value.to_integral_value():
        raise SettlementInputError(
            f"days_to_second_payment must be a whole number of days, not "
            f"{days_to_second_payment!r}"
        )
    days = int(days_value)
    if days < 0:
        raise SettlementInputError(
            f"days_to_second_payment cannot be negative, not {days}"
        )

    total_claim = principal + interest

    # The lever: waive interest first, then split what remains.
    interest_waived = rupees(interest * as_percent(waiver))
    interest_paid = interest - interest_waived
    principal_paid = principal  # principal is never waived
    total_payable = principal_paid + interest_paid

    upfront_amount = rupees(total_payable * as_percent(upfront))
    second_amount = total_payable - upfront_amount

    payments = [
        SettlementPayment(kind=PAYMENT_UPFRONT, days_from_now=0, amount=upfront_amount),
        SettlementPayment(kind=PAYMENT_SECOND, days_from_now=days, amount=second_amount),
    ]

    assumptions = [
        ASSUMPTION_WAIVER_ON_INTEREST,
        ASSUMPTION_UPFRONT_ON_PAYABLE,
        ASSUMPTION_NO_DISCOUNTING,
        ASSUMPTION_ROUNDING,
        (
            "The supplier's net recovery is nominal cash: principal recovered plus "
            "interest not waived. It is not reduced for the delay in receiving the "
            "second payment, and it excludes every buyer-cost line."
        ),
        (
            f"waiver_pct = {waiver} and upfront_pct = {upfront} are the negotiator's "
            "inputs, not statutory figures; changing either changes only this split, "
            "never the claim the evaluation computed."
        ),
    ]

    return SettlementResult(
        total_claim=total_claim,
        interest_waived=interest_waived,
        interest_paid=interest_paid,
        principal_paid=principal_paid,
        total_payable=total_payable,
        payments=payments,
        net_recovery=total_payable,
        upfront_pct=upfront,
        waiver_pct=waiver,
        days_to_second_payment=days,
        assumptions=assumptions,
    )
