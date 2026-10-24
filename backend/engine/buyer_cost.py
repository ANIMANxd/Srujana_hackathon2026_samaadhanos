"""buyer_cost.py — the three buyer-cost lines (architecture.md section 6.4).

Three separate lines, **never summed** (golden rule 8). This module returns no
combined figure and offers no way to build one:

1. **Permanent loss** — interest accrued is not deductible, so
   `interest_non_deductible` is the ledger's interest and nothing else. The
   43B(h) tax timing effect is deliberately kept out of it (trap 3).
   `pretax_equivalent_rate_pct = statutory_rate / (1 - buyer_tax_rate)` makes the
   rate the buyer would have had to earn to be indifferent.
2. **Deferral** — each 31 March in `[due_date, calculation_date]` on or after
   `section_43bh_first_fy`, where principal is still outstanding, is a
   checkpoint. Per checkpoint: `unpaid_principal`,
   `tax_timing_effect = unpaid_principal x tax_rate`, and a deferral cost of
   `tax_timing_effect x cost_of_capital x years_deferred` from the request
   inputs. `applies` is false when no checkpoint qualifies.
3. **Disclosure** — the s.22 audited-accounts disclosure always. Gated pressure
   points appear **only** when their `gated_features` flag is true, which
   defaults to false (OQ-8, V9 uncaptured).

`statutory_rate_pct`, `buyer_tax_rate_pct`, `cost_of_capital_pct` and
`years_deferred` are request inputs; the FY floor and the gates come from
config. Pure: no file I/O, no clock.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.dates import fy_ends_inclusive
from backend.engine.gate import GateCitation, GateWarning
from backend.engine.money import Paisa, as_percent, parse_money, rupees

# Warning codes this module can raise.
WARNING_MISSING_STATUTE_CONSTANT = "MISSING_STATUTE_CONSTANT"
WARNING_UNVERIFIED_GATED_FEATURE = "UNVERIFIED_GATED_FEATURE"

# The disclosure item section 6.4 requires on every evaluation.
S22_DISCLOSURE_ID = "s22_disclosure"
S22_DISCLOSURE_TEXT = (
    "s.22 disclosure: amounts payable to a micro or small enterprise must be "
    "disclosed in the buyer's audited accounts."
)

# Gated pressure points, emitted only when the matching config flag is true.
# Wording is limited to what section 6.4 and OQ-8 name; no section number beyond
# the one in the config key itself is asserted (golden rule 1).
GATED_PRESSURE_POINTS: dict[str, str] = {
    "gst_itc_180d": (
        "GST input tax credit reversal: the buyer may lose input tax credit on an "
        "invoice left unpaid beyond 180 days."
    ),
    "msme1_return": (
        "MSME-1 return: unpaid dues to a micro or small enterprise are reportable in "
        "the buyer's MSME-1 filing."
    ),
    "s19_deposit": (
        "Appeal deposit: filing an appeal against the resulting demand may require a "
        "deposit under s.19."
    ),
}


class BuyerCostInputError(ValueError):
    """An input cannot be used for buyer-cost math. Plain English, no guessing."""


# ------------------------------------------------------------ result types ----


@dataclass(frozen=True)
class PermanentLoss:
    """Interest that cannot be deducted. Never carries a tax timing figure."""

    interest_non_deductible: Decimal
    pretax_equivalent_rate_pct: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "interest_non_deductible": self.interest_non_deductible,
            "pretax_equivalent_rate_pct": self.pretax_equivalent_rate_pct,
        }


@dataclass(frozen=True)
class DeferralCheckpoint:
    """One 31 March at which principal was still unpaid."""

    fy_end: date
    unpaid_principal: Decimal
    tax_timing_effect: Decimal
    deferral_cost: Decimal  # engine-internal; the contract carries the total only

    def to_dict(self) -> dict[str, object]:
        # deferral_cost is deliberately not emitted: section 8.3's checkpoint has
        # exactly fy_end, unpaid_principal and tax_timing_effect.
        return {
            "fy_end": self.fy_end,
            "unpaid_principal": self.unpaid_principal,
            "tax_timing_effect": self.tax_timing_effect,
        }


@dataclass(frozen=True)
class Deferral:
    applies: bool
    checkpoints: list[DeferralCheckpoint]
    deferral_cost: Decimal | None
    cost_of_capital_pct: Decimal
    years_deferred: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "applies": self.applies,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "deferral_cost": self.deferral_cost,
            "inputs": {
                "cost_of_capital_pct": self.cost_of_capital_pct,
                "years_deferred": self.years_deferred,
            },
        }


@dataclass(frozen=True)
class DisclosureFlag:
    id: str
    text: str
    verified: bool

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "text": self.text, "verified": self.verified}


@dataclass(frozen=True)
class PressurePoint:
    id: str
    text: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "text": self.text}


@dataclass(frozen=True)
class BuyerCostResult:
    """The three lines side by side, plus what the response needs to cite them.

    There is deliberately no `total` field and no method that produces one
    (golden rule 8). `to_dict()` emits exactly the four keys of the contract's
    `BuyerCost`.
    """

    permanent_loss: PermanentLoss
    deferral: Deferral
    disclosure_flags: list[DisclosureFlag]
    pressure_points: list[PressurePoint]
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "permanent_loss": self.permanent_loss.to_dict(),
            "deferral": self.deferral.to_dict(),
            "disclosure_flags": [f.to_dict() for f in self.disclosure_flags],
            "other_pressure_points": [p.to_dict() for p in self.pressure_points],
        }


# ------------------------------------------------------------------ helpers ----


def _cite(config: StatuteConfig, key: str, rule: str) -> GateCitation:
    """A citation for one config key; reading it records usage (section 5)."""
    entry = config.entry(key)
    return GateCitation(
        id=f"buyer_cost.{key}",
        rule=rule,
        statute_ref=entry.source_ref,
        config_key=key,
        verified=entry.verified,
    )


def _fy_start_year(label: str) -> int:
    """Start year of a financial-year label such as "2023-24".

    Purely a way to order financial years so `section_43bh_first_fy` can be
    compared against a checkpoint; it reads no law, it orders one config string.
    """
    head = str(label).split("-")[0].strip()
    try:
        return int(head)
    except ValueError as exc:
        raise ConfigError(
            f"section_43bh_first_fy should look like \"2023-24\", not {label!r}; "
            "the deferral checkpoints cannot be ordered against it"
        ) from exc


def _principal_at(
    timeline: Sequence[tuple[date, Decimal]], on: date
) -> Decimal | None:
    """Principal bucket in force on `on`.

    `timeline` is (effective from, balance) ascending, seeded at date.min. Returns
    None when the timeline holds nothing on or before `on`, which is a caller
    error rather than a value to guess at.
    """
    best: tuple[date, Decimal] | None = None
    for when, balance in sorted(timeline, key=lambda item: item[0]):
        if when <= on:
            best = (when, balance)
    return None if best is None else best[1]


def _tax_rate(value) -> Decimal:
    """A buyer tax rate as a percentage; must leave (1 - rate) usable."""
    rate = parse_money(value)
    if rate < 0 or rate >= 100:
        raise BuyerCostInputError(
            f"the buyer tax rate must be between 0 and 100 percent, not {rate}; "
            "at 100 percent the pretax equivalent has no finite value"
        )
    return rate


# --------------------------------------------------------------- the rule ----


def evaluate_buyer_cost(
    config: StatuteConfig,
    *,
    interest_total,
    statutory_rate_pct,
    buyer_tax_rate_pct,
    due_date: date,
    calculation_date: date,
    cost_of_capital_pct,
    years_deferred,
    principal_timeline: Sequence[tuple[date, Decimal]],
) -> BuyerCostResult:
    """Build the three buyer-cost lines (section 6.4).

    `interest_total` is the accrued interest from the ledger, `statutory_rate_pct`
    the rate in force during the delay under the active rate mode, and the other
    three numerics are request inputs. `principal_timeline` comes from
    interest.py and supplies the principal outstanding at each 31 March.

    The three lines are returned separately and never added together.
    """
    citations: list[GateCitation] = []
    warnings: list[GateWarning] = []
    assumptions: list[str] = []

    accrued = parse_money(interest_total)
    if accrued < 0:
        raise BuyerCostInputError("interest_total cannot be negative")
    rate_pct = parse_money(statutory_rate_pct)
    tax_pct = _tax_rate(buyer_tax_rate_pct)
    capital_pct = parse_money(cost_of_capital_pct)
    deferred_years = parse_money(years_deferred)
    if capital_pct < 0:
        raise BuyerCostInputError(f"cost_of_capital_pct cannot be negative, not {capital_pct}")
    if deferred_years < 0:
        raise BuyerCostInputError(f"years_deferred cannot be negative, not {deferred_years}")

    # -- line 1: permanent loss ------------------------------------------
    # statutory_rate / (1 - tax rate), both as percentages, so the result is a
    # percentage: 16.50 / (1 - 0.312) = 23.98. ROUND_HALF_UP is spelled out
    # because Decimal's default is half-even, which would disagree with the
    # ledger's rounding (section 6).
    pretax_rate = (rate_pct / (Decimal("1") - as_percent(tax_pct))).quantize(
        Paisa, rounding=ROUND_HALF_UP
    )
    permanent_loss = PermanentLoss(
        interest_non_deductible=accrued,
        pretax_equivalent_rate_pct=pretax_rate,
    )

    # -- line 2: deferral --------------------------------------------------
    if calculation_date < due_date:
        fy_ends: list[date] = []  # not yet past due: no checkpoint can have passed
    else:
        fy_ends = fy_ends_inclusive(due_date, calculation_date)

    first_fy_label: str | None = None
    eligible: list[date] = []
    if fy_ends:
        # Only read when there is a checkpoint to order, so an untouched constant
        # never shows up among the ones this computation relied on.
        entry = config.entry("section_43bh_first_fy")
        citations.append(
            _cite(
                config,
                "section_43bh_first_fy",
                "deferral checkpoints count only from the first FY in which s.43B(h) applies",
            )
        )
        if entry.value is None:
            warnings.append(
                GateWarning(
                    code=WARNING_MISSING_STATUTE_CONSTANT,
                    severity="WARN",
                    text=(
                        "The config has no value for section_43bh_first_fy, so the engine "
                        "cannot tell which financial years s.43B(h) reaches. No deferral "
                        "checkpoint was produced; this is an absence of a figure, not a "
                        "finding that the buyer owes nothing."
                    ),
                )
            )
        else:
            first_fy_label = str(entry.value)
            floor = _fy_start_year(first_fy_label)
            # A 31 March close belongs to the FY that began the previous April.
            eligible = [d for d in fy_ends if d.year - 1 >= floor]

    checkpoints: list[DeferralCheckpoint] = []
    total_cost = Decimal("0.00")
    for fy_end in eligible:
        if not principal_timeline:
            raise BuyerCostInputError(
                "principal_timeline is empty, so the principal outstanding on "
                f"{fy_end.isoformat()} is unknown; pass the timeline from interest.py"
            )
        raw_unpaid = _principal_at(principal_timeline, fy_end)
        if raw_unpaid is None:
            raise BuyerCostInputError(
                f"principal_timeline has no entry on or before {fy_end.isoformat()}"
            )
        unpaid = rupees(raw_unpaid)
        if unpaid <= 0:
            continue  # principal already cleared: nothing outstanding past the limit
        tax_effect = rupees(unpaid * as_percent(tax_pct))
        cost = rupees(tax_effect * as_percent(capital_pct) * deferred_years)
        checkpoints.append(
            DeferralCheckpoint(
                fy_end=fy_end,
                unpaid_principal=unpaid,
                tax_timing_effect=tax_effect,
                deferral_cost=cost,
            )
        )
        total_cost += cost

    applies = bool(checkpoints)
    deferral = Deferral(
        applies=applies,
        checkpoints=checkpoints,
        deferral_cost=total_cost if applies else None,
        cost_of_capital_pct=capital_pct,
        years_deferred=deferred_years,
    )

    # -- line 3: disclosure ------------------------------------------------
    # verified stays False: no V-ref captures the s.22 wording yet, so nothing
    # here may be presented as checked against the statute sheet.
    disclosure_flags = [
        DisclosureFlag(id=S22_DISCLOSURE_ID, text=S22_DISCLOSURE_TEXT, verified=False)
    ]

    citations.append(
        _cite(
            config,
            "gated_features",
            "gated buyer pressure points are emitted only when their flag is true",
        )
    )
    features = config.gated_features()
    pressure_points: list[PressurePoint] = []
    unverified_gated: list[str] = []
    for name, text in GATED_PRESSURE_POINTS.items():
        if features.get(name):
            pressure_points.append(PressurePoint(id=name, text=text))
            unverified_gated.append(name)
    # A flag the map does not know still deserves a row rather than silence.
    for name, enabled in sorted(features.items()):
        if enabled and name not in GATED_PRESSURE_POINTS:
            pressure_points.append(
                PressurePoint(id=name, text=f"Gated buyer pressure point: {name}.")
            )
            unverified_gated.append(name)

    if unverified_gated:
        gated_entry = config.entry("gated_features")
        warnings.append(
            GateWarning(
                code=WARNING_UNVERIFIED_GATED_FEATURE,
                severity="WARN",
                text=(
                    "These buyer pressure points are switched on but their rule is still "
                    f"an open question (OQ-8, source {gated_entry.source_ref}): "
                    + ", ".join(sorted(unverified_gated))
                    + ". Treat them as an unverified prompt for the buyer, not a stated "
                    "legal consequence."
                ),
            )
        )

    assumptions.extend(
        [
            "The three buyer-cost lines are reported separately and are never added "
            "into one number: what the buyer loses permanently, what it defers, and "
            "what it must disclose are different things.",
            "The interest figure is interest only. The s.43B(h) tax timing effect is "
            "reported on the deferral line and is never added to interest (trap 3).",
            f"pretax_equivalent_rate_pct = statutory rate / (1 - buyer tax rate), "
            f"rounded half-up to 0.01: {rate_pct} / (1 - {as_percent(tax_pct)}) = {pretax_rate}.",
            "Each deferral checkpoint is a 31 March in [due_date, calculation_date] on "
            "or after section_43bh_first_fy; its cost is rounded to 0.01 first and the "
            "line total is their sum, matching the ledger's per-row rounding.",
            "Checkpoint figures use the request's cost_of_capital_pct and "
            "years_deferred as given; the engine does not pick those defaults.",
        ]
    )
    if not applies:
        assumptions.append(
            "Deferral does not apply here because no qualifying 31 March checkpoint "
            "fell in the window with principal still unpaid."
        )

    return BuyerCostResult(
        permanent_loss=permanent_loss,
        deferral=deferral,
        disclosure_flags=disclosure_flags,
        pressure_points=pressure_points,
        citations=citations,
        warnings=warnings,
        assumptions=assumptions,
    )
