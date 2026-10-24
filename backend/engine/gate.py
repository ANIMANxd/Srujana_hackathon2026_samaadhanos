"""gate.py — the eligibility gate (architecture.md section 6.1).

Four checks, in order:

1. enterprise_class on the supply date, looked up in size_epochs. Medium and
   above fail. Reverse graduation is noted in the detail text.
2. silpi_chronology using the silpi_test_date config value. When that value is
   null the check returns passed=None with an OPEN_QUESTION warning, never a
   silent pass or fail (golden rule 1; OQ-2 is still open).
3. trader_exclusion from the NIC prefixes in trader_nic_prefixes.
4. activity_match, a risk flag only. It never blocks.

Status precedence for the pill (section 6.1):
    BARRED_SILPI > EXCLUDED_TRADER > EXCLUDED_MEDIUM > INSUFFICIENT_DATA > ELIGIBLE

When the gate blocks, downstream blocks are null with a warning, never zero:
a blocked case has no interest figure, not an interest figure of 0.00.

Every check emits a citation, and every check that reads a config value records
that usage, so StatuteConfig.warnings() reports the unverified constants this
gate actually relied on.

Pure module: the config and the case facts arrive as arguments. No file I/O, no
clock, no network.
"""

from dataclasses import dataclass
from datetime import date

from backend.engine.config import SizeEpoch, StatuteConfig

# Statuses, kept aligned with the JurisdictionStatus enum in backend/app/schemas.py.
STATUS_BARRED_SILPI = "BARRED_SILPI"
STATUS_EXCLUDED_TRADER = "EXCLUDED_TRADER"
STATUS_EXCLUDED_MEDIUM = "EXCLUDED_MEDIUM"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_ELIGIBLE = "ELIGIBLE"

# Precedence order, highest first (section 6.1).
STATUS_PRECEDENCE: tuple[str, ...] = (
    STATUS_BARRED_SILPI,
    STATUS_EXCLUDED_TRADER,
    STATUS_EXCLUDED_MEDIUM,
    STATUS_INSUFFICIENT_DATA,
    STATUS_ELIGIBLE,
)

# Warning and citation codes the gate can emit.
WARNING_OPEN_QUESTION = "OPEN_QUESTION"
WARNING_MISSING_SUPPLY_DATE = "MISSING_SUPPLY_DATE"
WARNING_NO_SIZE_EPOCH = "NO_SIZE_EPOCH"
WARNING_MISSING_ACTIVITY_DATA = "MISSING_ACTIVITY_DATA"
WARNING_TRADING_EVIDENCE_CONFLICT = "TRADING_EVIDENCE_CONFLICT"

CHECK_ENTERPRISE_CLASS = "enterprise_class"
CHECK_SILPI_CHRONOLOGY = "silpi_chronology"
CHECK_TRADER_EXCLUSION = "trader_exclusion"
CHECK_ACTIVITY_MATCH = "activity_match"

# Classes that fail the gate. Anything at or above medium is out (section 6.1).
BLOCKING_CLASSES: frozenset[str] = frozenset({"MEDIUM", "LARGE"})

# The alternative remedy wording for a blocked case (section 6.1). Cautious,
# sourced language: no promise of winning (golden rule in AGENTS.md section 7).
ALTERNATIVE_REMEDY = (
    "This route under the MSMED Act does not apply to this case. A civil claim for "
    "the price of goods or services remains available: a summary suit under Order "
    "XXXVII of the Code of Civil Procedure, filed in the appropriate civil court, "
    "and, where the amount or the parties place it beyond the small-cause route, the "
    "Commercial Courts Act. Take the case file to a licensed advocate before filing; "
    "this tool does not file anything and does not predict an outcome."
)


# ------------------------------------------------------------- result types ----


@dataclass(frozen=True)
class GateWarning:
    """One warning, shaped like the contract's warnings[] block."""

    code: str
    severity: str  # INFO | WARN | BLOCK, per the WarningSeverity enum
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "text": self.text}


@dataclass(frozen=True)
class GateCitation:
    """One citation, shaped like the contract's citations[] block (section 6)."""

    id: str
    rule: str
    statute_ref: str
    config_key: str | None
    verified: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "rule": self.rule,
            "statute_ref": self.statute_ref,
            "config_key": self.config_key,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class GateCheck:
    """One check row. passed=None means undecidable, not unasked (section 6.1)."""

    id: str
    passed: bool | None
    detail: str
    rule_ref: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "passed": self.passed, "detail": self.detail, "rule_ref": self.rule_ref}


@dataclass(frozen=True)
class GateResult:
    """The gate verdict plus everything the response needs to cite it.

    `blocked` is True for any status other than ELIGIBLE. Downstream blocks must
    be null with a warning when this is set, never zero.
    """

    status: str
    eligible: bool
    checks: list[GateCheck]
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]
    alternative_remedy: str | None

    @property
    def blocked(self) -> bool:
        return not self.eligible

    @property
    def insufficient_data(self) -> bool:
        return self.status == STATUS_INSUFFICIENT_DATA

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "eligible": self.eligible,
            "checks": [c.to_dict() for c in self.checks],
            "alternative_remedy": self.alternative_remedy,
            "citations": [c.to_dict() for c in self.citations],
            "warnings": [w.to_dict() for w in self.warnings],
            "assumptions": list(self.assumptions),
        }


# ------------------------------------------------------------------ helpers ----


def _citations_for(config: StatuteConfig, *keys: str) -> list[GateCitation]:
    """Citations for the given config keys, carrying each key's verified flag.

    Reading a config value also records it as used, so the UNVERIFIED_CONSTANT
    warnings cover exactly the constants this gate relied on.
    """
    out: list[GateCitation] = []
    for key in keys:
        entry = config.entry(key)
        out.append(
            GateCitation(
                id=f"gate.{key}",
                rule=f"gate reads {key} from the statute config",
                statute_ref=entry.source_ref,
                config_key=key,
                verified=entry.verified,
            )
        )
    return out


def _worst_status(statuses: list[str]) -> str:
    """The highest-precedence status in `statuses` (section 6.1 ordering)."""
    for candidate in STATUS_PRECEDENCE:
        if candidate in statuses:
            return candidate
    return STATUS_ELIGIBLE


# ------------------------------------------------------------- the checks ----


def _check_enterprise_class(
    config: StatuteConfig,
    enterprise_class: str,
    supply_date: date | None,
    investment_cr,
    turnover_cr,
) -> tuple[GateCheck, list[GateCitation], list[GateWarning], list[str]]:
    """Class on the supply date via size_epochs. Medium and above fail."""
    citations = _citations_for(config, "size_epochs")
    warnings: list[GateWarning] = []
    assumptions: list[str] = []
    rule_ref = "gate.enterprise_class"

    if supply_date is None:
        # No anchor date: do not guess. Note that supply_date defaults to the
        # delivery date at the API boundary; that defaulting is not done here.
        warnings.append(
            GateWarning(
                code=WARNING_MISSING_SUPPLY_DATE,
                severity="WARN",
                text=(
                    "There is no supply date on this case, so the enterprise class "
                    "cannot be looked up for the date the supply happened. Add the "
                    "delivery date, which stands in for the supply date when it is "
                    "absent. The status below is not a pass."
                ),
            )
        )
        return (
            GateCheck(
                id=CHECK_ENTERPRISE_CLASS,
                passed=None,
                detail=(
                    "Cannot tell: the case has no supply date to look the class up on. "
                    "This is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    epoch: SizeEpoch | None = config.size_limits_on(supply_date)
    if epoch is None:
        warnings.append(
            GateWarning(
                code=WARNING_NO_SIZE_EPOCH,
                severity="WARN",
                text=(
                    f"No size epoch in the config covers {supply_date.isoformat()}, so the "
                    "investment and turnover ceilings for that date are unknown. Add an "
                    "earlier size epoch, or check the supply date."
                ),
            )
        )
        return (
            GateCheck(
                id=CHECK_ENTERPRISE_CLASS,
                passed=None,
                detail=(
                    f"Cannot tell: the config has no size epoch covering "
                    f"{supply_date.isoformat()}. This is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    stated = enterprise_class.upper()
    detail_bits: list[str] = []

    if stated == "UNKNOWN":
        # No figures and no stated class: report insufficient data, not a pass.
        return (
            GateCheck(
                id=CHECK_ENTERPRISE_CLASS,
                passed=None,
                detail=(
                    "The supplier's class is unknown and no investment or turnover "
                    "figures were given, so the ceilings for "
                    f"{supply_date.isoformat()} cannot be applied. This is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    limits = getattr(epoch, stated.lower(), None)
    if limits is None:
        # A class the size epochs do not name. Refuse rather than guess.
        return (
            GateCheck(
                id=CHECK_ENTERPRISE_CLASS,
                passed=None,
                detail=(
                    f"Cannot tell: {stated} is not one of the classes the size epochs "
                    "define (micro, small, medium). This is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    if investment_cr is None and turnover_cr is None:
        # Class asserted with nothing to check it against.
        detail_bits.append(
            f"The case states {stated.lower()}, with no investment or turnover figure "
            f"to check against the ceilings in force on {supply_date.isoformat()} "
            f"(investment up to {limits.investment_cr} crore, turnover up to "
            f"{limits.turnover_cr} crore)."
        )
        assumptions.append(
            f"The supplier is treated as {stated.lower()} because the case says so and "
            "gave no figures to check it against; the figures were not verified."
        )
        passed = False if stated in BLOCKING_CLASSES else True
        detail_bits.append("This is a stated class, not a measured one.")
        return (
            GateCheck(id=CHECK_ENTERPRISE_CLASS, passed=passed, detail=" ".join(detail_bits), rule_ref=rule_ref),
            citations,
            warnings,
            assumptions,
        )

    # Measured against the ceilings in force on the supply date.
    over: list[str] = []
    if investment_cr is not None and investment_cr > limits.investment_cr:
        over.append(f"investment {investment_cr} crore exceeds {limits.investment_cr} crore")
    if turnover_cr is not None and turnover_cr > limits.turnover_cr:
        over.append(f"turnover {turnover_cr} crore exceeds {limits.turnover_cr} crore")

    if over:
        detail_bits.append(
            f"Measured against the ceilings in force on {supply_date.isoformat()} "
            f"(investment up to {limits.investment_cr} crore, turnover up to "
            f"{limits.turnover_cr} crore): " + "; ".join(over) + "."
        )
        detail_bits.append(
            "This is reverse graduation: a supplier that once qualified can stop "
            "qualifying once its figures grow past the ceilings. The date the supply "
            "happened decides which ceilings apply."
        )
        return (
            GateCheck(id=CHECK_ENTERPRISE_CLASS, passed=False, detail=" ".join(detail_bits), rule_ref=rule_ref),
            citations,
            warnings,
            assumptions,
        )

    detail_bits.append(
        f"Within the ceilings in force on {supply_date.isoformat()} (investment up to "
        f"{limits.investment_cr} crore, turnover up to {limits.turnover_cr} crore)."
    )
    return (
        GateCheck(id=CHECK_ENTERPRISE_CLASS, passed=True, detail=" ".join(detail_bits), rule_ref=rule_ref),
        citations,
        warnings,
        assumptions,
    )


def _check_silpi_chronology(
    config: StatuteConfig,
    contract_date: date | None,
    supply_date: date | None,
) -> tuple[GateCheck, list[GateCitation], list[GateWarning], list[str]]:
    """The Silpi works-contract test date. A null config value is undecidable."""
    citations = _citations_for(config, "silpi_test_date")
    warnings: list[GateWarning] = []
    assumptions: list[str] = []
    rule_ref = "gate.silpi_chronology"

    test_date = config.silpi_test_date()
    if test_date is None:
        # OQ-2 is open. Return null plus an OPEN_QUESTION warning, never a pass.
        warnings.append(
            GateWarning(
                code=WARNING_OPEN_QUESTION,
                severity="WARN",
                text=(
                    "Whether the Silpi works-contract test runs from the date of the "
                    "contract or from the date of supply is still an open question "
                    "(OQ-2, source V4). The config value silpi_test_date is null, so "
                    "this check cannot decide. It is neither a pass nor a fail, and no "
                    "silpi bar is being applied to this case."
                ),
            )
        )
        return (
            GateCheck(
                id=CHECK_SILPI_CHRONOLOGY,
                passed=None,
                detail=(
                    "Cannot tell: whether the Silpi test runs from the contract date or "
                    "the supply date is unresolved (OQ-2). This is not a pass, and no "
                    "silpi bar is applied."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    test_date = str(test_date).upper()
    anchor = contract_date if test_date == "CONTRACT" else supply_date
    if anchor is None:
        which = "contract date" if test_date == "CONTRACT" else "supply date"
        return (
            GateCheck(
                id=CHECK_SILPI_CHRONOLOGY,
                passed=None,
                detail=(
                    f"Cannot tell: the Silpi test runs from the {which} (config "
                    f"silpi_test_date = {test_date}), and this case has no {which}. "
                    "This is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    # The config value is set, so the chronology has an anchor and passes. Whether
    # this supplier is a works contract at all is a separate question the gate does
    # not decide; it only records that the chronology could be fixed.
    assumptions.append(
        f"The Silpi chronology is read from the {test_date.lower()} because "
        f"silpi_test_date = {test_date} (OQ-2). If V4 settles that differently, this "
        "check changes."
    )
    return (
        GateCheck(
            id=CHECK_SILPI_CHRONOLOGY,
            passed=True,
            detail=(
                f"The Silpi chronology can be fixed: the config runs the test from the "
                f"{test_date.lower()} ({anchor.isoformat()}), and that date is present."
            ),
            rule_ref=rule_ref,
        ),
        citations,
        warnings,
        assumptions,
    )


def _check_trader_exclusion(
    config: StatuteConfig,
    nic_codes: list[str],
    activity: str,
) -> tuple[GateCheck, list[GateCitation], list[GateWarning], list[str]]:
    """NIC prefixes. A trading NIC excludes; a stated TRADING activity corroborates."""
    citations = _citations_for(config, "trader_nic_prefixes")
    warnings: list[GateWarning] = []
    assumptions: list[str] = []
    rule_ref = "gate.trader_exclusion"

    prefixes = [str(p) for p in config.trader_nic_prefixes()]
    codes = [str(c).strip() for c in (nic_codes or []) if str(c).strip()]
    stated_trading = str(activity or "").upper() == "TRADING"

    matches = sorted({c for c in codes for p in prefixes if c.startswith(p)})

    if matches:
        return (
            GateCheck(
                id=CHECK_TRADER_EXCLUSION,
                passed=False,
                detail=(
                    "The supplier's NIC codes " + ", ".join(matches) + " fall in a trading "
                    "division (prefixes " + ", ".join(prefixes) + "), so the trading "
                    "exclusion applies."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    if codes and not stated_trading:
        return (
            GateCheck(
                id=CHECK_TRADER_EXCLUSION,
                passed=True,
                detail=(
                    "The supplier's NIC codes (" + ", ".join(codes) + ") do not fall in a "
                    "trading division (prefixes " + ", ".join(prefixes) + ")."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    if codes and stated_trading:
        # The NIC codes place the supplier outside every trading division, but the
        # activity says TRADING. Deciding either way would guess (section 6), so
        # the check reports neither pass nor fail and names the conflict.
        warnings.append(
            GateWarning(
                code=WARNING_TRADING_EVIDENCE_CONFLICT,
                severity="WARN",
                text=(
                    "The case states the activity as TRADING, but the NIC codes given ("
                    + ", ".join(codes)
                    + ") fall outside the trading divisions (prefixes "
                    + ", ".join(prefixes)
                    + "). The two sources disagree, so the trading exclusion could not "
                    "be decided. Correct the activity or the NIC codes before relying "
                    "on this result."
                ),
            )
        )
        return (
            GateCheck(
                id=CHECK_TRADER_EXCLUSION,
                passed=None,
                detail=(
                    "Cannot tell: the case states the activity as TRADING while the NIC "
                    "codes (" + ", ".join(codes) + ") do not fall in a trading division. "
                    "The evidence conflicts, so this is not a pass."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    if stated_trading:
        # No NIC codes, but the case says TRADING. That is evidence enough to
        # report a trader exclusion, with the missing NIC codes named.
        assumptions.append(
            "The supplier is treated as trading because the case states the activity as "
            "TRADING and gave no NIC codes to check it against."
        )
        return (
            GateCheck(
                id=CHECK_TRADER_EXCLUSION,
                passed=False,
                detail=(
                    "No NIC codes were given, but the case states the activity as "
                    "TRADING, which is the trading exclusion on its own terms."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    # Nothing to judge on. Not a pass.
    return (
        GateCheck(
            id=CHECK_TRADER_EXCLUSION,
            passed=None,
            detail=(
                "Cannot tell: this case has no NIC codes and does not state the activity "
                "as trading. This is not a pass."
            ),
            rule_ref=rule_ref,
        ),
        citations,
        warnings,
        assumptions,
    )


def _check_activity_match(
    config: StatuteConfig,
    activity: str,
    nic_codes: list[str],
) -> tuple[GateCheck, list[GateCitation], list[GateWarning], list[str]]:
    """A risk flag only (section 6.1). Never blocks, never changes the status."""
    citations = _citations_for(config, "trader_nic_prefixes")
    warnings: list[GateWarning] = []
    assumptions: list[str] = []
    rule_ref = "gate.activity_match"

    stated = str(activity or "").upper()
    codes = [str(c).strip() for c in (nic_codes or []) if str(c).strip()]
    prefixes = [str(p) for p in config.trader_nic_prefixes()]
    nic_says_trading = any(c.startswith(p) for c in codes for p in prefixes)

    if not codes and not stated:
        warnings.append(
            GateWarning(
                code=WARNING_MISSING_ACTIVITY_DATA,
                severity="INFO",
                text=(
                    "Neither an activity nor an NIC code was given, so the activity match "
                    "could not be checked. This is only a risk flag and does not affect "
                    "eligibility."
                ),
            )
        )
        return (
            GateCheck(
                id=CHECK_ACTIVITY_MATCH,
                passed=None,
                detail=(
                    "Cannot tell: no activity and no NIC codes. This is a risk flag only "
                    "and does not affect eligibility."
                ),
                rule_ref=rule_ref,
            ),
            citations,
            warnings,
            assumptions,
        )

    agrees = (stated == "TRADING" and nic_says_trading) or (
        stated != "TRADING" and codes and not nic_says_trading
    )
    if agrees:
        detail = (
            "The stated activity and the NIC codes agree. This is a risk flag only and "
            "does not affect eligibility."
        )
    else:
        detail = (
            "The stated activity and the NIC codes do not clearly agree. This is a risk "
            "flag only and does not affect eligibility; it never blocks on its own."
        )
    return (
        GateCheck(id=CHECK_ACTIVITY_MATCH, passed=agrees, detail=detail, rule_ref=rule_ref),
        citations,
        warnings,
        assumptions,
    )


# --------------------------------------------------------------------- gate ----


def evaluate_gate(
    config: StatuteConfig,
    *,
    enterprise_class: str,
    activity: str,
    nic_codes: list[str],
    contract_date: date | None,
    supply_date: date | None,
    investment_cr=None,
    turnover_cr=None,
) -> GateResult:
    """Run the four checks in order and resolve the status (section 6.1).

    `investment_cr` and `turnover_cr` are Decimals, or None when the case does not
    state them. All date anchors are explicit arguments; nothing here defaults a
    missing supply date to the delivery date, because that default belongs at the
    API boundary where the request is known.

    The result carries the checks, a citation per config key read, every warning
    the checks raised, and the alternative remedy when the gate blocks.
    """
    enterprise_check, e_cites, e_warns, e_assume = _check_enterprise_class(
        config, enterprise_class, supply_date, investment_cr, turnover_cr
    )
    silpi_check, s_cites, s_warns, s_assume = _check_silpi_chronology(
        config, contract_date, supply_date
    )
    trader_check, t_cites, t_warns, t_assume = _check_trader_exclusion(
        config, nic_codes, activity
    )
    activity_check, a_cites, a_warns, a_assume = _check_activity_match(
        config, activity, nic_codes
    )

    checks = [enterprise_check, silpi_check, trader_check, activity_check]
    citations = e_cites + s_cites + t_cites + a_cites
    warnings = e_warns + s_warns + t_warns + a_warns
    assumptions = e_assume + s_assume + t_assume + a_assume

    # Resolve the status by precedence. activity_match is excluded on purpose:
    # it is a risk flag and never blocks (section 6.1).
    statuses: list[str] = []
    if silpi_check.passed is False:
        statuses.append(STATUS_BARRED_SILPI)
    if trader_check.passed is False:
        statuses.append(STATUS_EXCLUDED_TRADER)
    if enterprise_check.passed is False:
        statuses.append(STATUS_EXCLUDED_MEDIUM)
    if silpi_check.passed is None or enterprise_check.passed is None:
        statuses.append(STATUS_INSUFFICIENT_DATA)
    if not statuses:
        statuses.append(STATUS_ELIGIBLE)

    status = _worst_status(statuses)
    eligible = status == STATUS_ELIGIBLE
    return GateResult(
        status=status,
        eligible=eligible,
        checks=checks,
        citations=citations,
        warnings=warnings,
        assumptions=assumptions,
        alternative_remedy=None if eligible else ALTERNATIVE_REMEDY,
    )


def blocked_downstream_note(result: GateResult) -> GateWarning:
    """The warning to attach when downstream blocks are nulled for a blocked case.

    Section 6.1: a blocked case skips the interest and buyer-cost blocks, and
    they must come back null with a warning, never zero. This is that warning, so
    a null on screen is explained rather than looking like a missing number.
    """
    return GateWarning(
        code="GATE_BLOCKED",
        severity="BLOCK",
        text=(
            f"The eligibility gate returned {result.status}, so no interest, buyer cost "
            "or limitation figures were computed for this case. Those blocks are empty "
            "because no calculation ran, not because the amounts are zero."
        ),
    )
