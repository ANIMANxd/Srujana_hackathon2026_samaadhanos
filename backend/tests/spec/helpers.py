"""Config reads, request builders and hand-math helpers for the spec suite.

Test-author rules (AGENTS.md section 3): this suite works from
`docs/architecture.md`, `docs/open-questions.md`, the statute sheet checklist
and the statute config - **it never opens `backend/engine/**`**. So every
expectation here is either:

- read from the statute config through the config loader (no statutory
  literal appears in a test), or
- written out by hand from the formulas in architecture.md section 6, with
  the arithmetic spelled out in a comment above the assertion it supports.

The suite talks to the HTTP interface only (`POST /api/v1/evaluate-case`):
that is the public evaluate interface, and it is also where malformed input
must produce the contract's error envelope rather than a stack trace.
"""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from backend.app.config_loader import load_config

# --------------------------------------------------------------- config ----

CONFIG = load_config()


def const(key: str):
    """The configured *value* for a statutory key (never a literal here)."""
    return CONFIG[key]["value"]


def source_ref(key: str) -> str:
    return str(CONFIG[key]["source_ref"])


def is_verified(key: str) -> bool:
    return bool(CONFIG[key]["verified"])


MULTIPLIER = const("interest_multiplier")  # s.16 multiple of the Bank Rate
WINDOW_DAYS = const("objection_window_days")  # s.2(b) written-objection window
CREDIT_CAP_DAYS = const("credit_cap_days")  # s.15 proviso cap
NO_AGREEMENT_DAYS = const("no_agreement_days")  # s.15 period, no written terms
DAY_COUNT = const("day_count_fraction_days")  # convention: section 5
SECTION_43BH_FIRST_FY = const("section_43bh_first_fy")
RATE_MODE_DEFAULT = const("rate_mode_default")
APPROPRIATION_MODE_DEFAULT = const("appropriation_mode_default")
SILPI_TEST_DATE = const("silpi_test_date")  # null until V4 is captured (OQ-2)
LIMITATION_YEARS = const("limitation_years")  # null until V7 (OQ-6)
TRADER_PREFIXES = tuple(const("trader_nic_prefixes"))
SMALL_CEILING_INVESTMENT_CR = Decimal(
    const("size_epochs")[0]["small"]["investment_cr"]
)  # the dated set: 2025-04-01 onwards

# [(iso_from, bank_rate_pct)] as configured; V1 is uncaptured (OQ/CHECKLIST).
EPOCHS = sorted(
    (epoch["from"], Decimal(epoch["bank_rate_pct"]))
    for epoch in const("bank_rate_epochs")
    if epoch["from"] is not None
)


# ------------------------------------------------- hand-math primitives ----


def bank_rate_on(iso: str) -> Decimal:
    """Bank Rate in force on a date: the latest epoch that has started.

    Architecture 6.3: rate segments split at epoch boundaries; the segment
    starting on the epoch's first day carries that day's rate (half-open
    intervals, open-questions CQ-13).
    """
    rate = None
    for start, value in EPOCHS:
        if start <= iso:
            rate = value
    assert rate is not None, f"no configured epoch covers {iso} (V1 uncaptured)"
    return rate


def statutory_rate_on(iso: str) -> Decimal:
    """Architecture 6.3: statutory rate = interest_multiplier x Bank Rate."""
    return (Decimal(str(MULTIPLIER)) * bank_rate_on(iso)).quantize(Decimal("0.01"))


def rupees(value) -> Decimal:
    """Half-up to 0.01, the rounding the architecture fixes for every row."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def simple_interest(principal, rate_pct, days) -> Decimal:
    """Hand formula from architecture 6.3: rate x days / day_count.

    `principal` is the balance the period opens with (capitalised at rests),
    `rate_pct` the statutory rate for that period, `days` the day count
    between the period's ends (dates subtracted on the calendar).
    """
    return rupees(
        Decimal(str(principal))
        * (Decimal(str(rate_pct)) / Decimal("100"))
        * Decimal(days)
        / Decimal(str(DAY_COUNT))
    )


def days_between(start_iso: str, end_iso: str) -> int:
    """Calendar days from start to end, as 6.3 counts them for a stub."""
    return (date.fromisoformat(end_iso) - date.fromisoformat(start_iso)).days


def add_days(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def month_end_step(iso: str, months: int) -> str:
    """`appointed_day + k months`, end-of-month clamped (6.3).

    Written out here so a leap-year expectation is the test's own, not the
    engine's: 2028-01-31 + 1 month = 2028-02-29.
    """
    from dateutil.relativedelta import relativedelta

    return (date.fromisoformat(iso) + relativedelta(months=months)).isoformat()


# --------------------------------------------------------------- requests ----

DEFAULT_EVIDENCE = {
    "items": [
        {"kind": "PO", "present": True, "ref": "spec-po"},
        {"kind": "INVOICE", "present": True, "ref": "spec-invoice"},
        {"kind": "DELIVERY_PROOF", "present": True, "ref": "spec-lr"},
        {"kind": "WHATSAPP", "present": False, "ref": None},
        {"kind": "UDYAM", "present": True, "ref": "spec-udyam"},
        {"kind": "GST_RETURN", "present": True, "ref": "spec-gst"},
    ]
}

# Round numbers on purpose: principal 365000 divides by the 365-day day count
# exactly, so hand interest lands on whole rupees (see simple_interest).
DEFAULT_TRANSACTION = {
    "contract_date": None,
    "supply_date": "2026-06-01",
    "invoice_date": "2026-06-01",
    "delivery_date": "2026-06-01",
    "principal": "365000.00",
    "written_credit_days": None,
    "calculation_date": "2026-06-27",
    "years_deferred": "1.00",
}

DEFAULT_SUPPLIER = {
    "name": "Spec Supplier (synthetic)",
    "udyam_number": "UDYAM-SYN-000000009",
    "enterprise_class": "MICRO",
    "activity": "MANUFACTURING",
    "nic_codes": ["25990"],
    "udyam_registration_date": "2020-01-01",
    "investment_cr": "1.00",
    "turnover_cr": "5.00",
}

DEFAULT_BUYER = {
    "name": "Spec Buyer (synthetic)",
    "gstin": None,
    "tax_rate_pct": "30",
    "cost_of_capital_pct": "12",
}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def base_request(case_id: str = "spec-case", **overrides) -> dict:
    """A valid round-number request; `overrides` deep-merge into the defaults.

    Every scenario in this suite starts here, so a failing test is about the
    rule under test rather than about scaffolding.
    """
    request = {
        "contract_version": "1.0",
        "case_id": case_id,
        "supplier": deepcopy(DEFAULT_SUPPLIER),
        "buyer": deepcopy(DEFAULT_BUYER),
        "transaction": deepcopy(DEFAULT_TRANSACTION),
        "objections": [],
        "part_payments": [],
        "acknowledgments": [],
        "evidence": deepcopy(DEFAULT_EVIDENCE),
        "config_overrides": None,
    }
    return _deep_merge(request, overrides)


# ------------------------------------------------------------- the calls ----


def post_evaluate(client, request: dict):
    """Raw POST, so malformed-input tests can look at a non-200 answer."""
    return client.post("/api/v1/evaluate-case", json=request)


def evaluate_ok(client, request: dict) -> dict:
    """POST and require the happy path, quoting the body if it refuses."""
    response = post_evaluate(client, request)
    assert (
        response.status_code == 200
    ), f"expected 200, got {response.status_code}: {response.text[:800]}"
    body = response.json()
    assert "error" not in body, f"unexpected error envelope: {body}"
    return body


def warning_codes(body: dict) -> list[str]:
    return [warning["code"] for warning in body.get("warnings", [])]


def warning_texts(body: dict) -> str:
    return " ".join(warning["text"] for warning in body.get("warnings", []))


def assumptions_blob(body: dict) -> str:
    return " ".join(body.get("assumptions", []))


def unverified_keys_mentioned(body: dict) -> set[str]:
    """Config keys an UNVERIFIED_CONSTANT warning names (architecture 5: an
    unverified constant the computation uses must surface a warning)."""
    keys = set()
    for warning in body.get("warnings", []):
        if warning["code"] != "UNVERIFIED_CONSTANT":
            continue
        for key in CONFIG:
            if key.startswith("_"):
                continue
            if key in warning["text"]:
                keys.add(key)
    return keys


# ------------------------------------------------------ shared assertions ----


def assert_ledger_consistent(
    financials: dict, *, first_from=None, last_to=None
) -> Decimal:
    """Every row balances, the balance carries forward, and the rows sum up.

    Architecture 6.3 (rows by rest/payment/stub, rounded half-up per row,
    interest capitalised onto the balance at each rest) and section 11
    ("Decimal rounding totals equal the sum of rows"), plus the row identity
    documented in open-questions CQ-17: `opening + interest - payment ==
    closing` for each row.

    Rows are *events*: a day with nothing to book (two payments in a stretch
    where no interest can accrue) may have no row at all, so the dates are not
    required to abut - but the balance must carry from one row's closing to the
    next row's opening, or money would vanish between rows. Each scenario also
    checks its hand-computed total, which is what catches an unpriced day.
    """
    rows = financials["ledger"]
    assert rows, "a computed claim must have at least one ledger row"
    interest_sum = Decimal("0.00")
    previous_closing = None
    for index, row in enumerate(rows):
        opening = Decimal(row["opening"])
        accrued = Decimal(row["interest"])
        payment = Decimal(row["payment"])
        closing = Decimal(row["closing"])
        assert (
            opening + accrued - payment == closing
        ), f"row {index} does not balance: {opening} + {accrued} - {payment} != {closing}"
        if previous_closing is not None:
            assert opening == previous_closing, (
                f"row {index} opens at {opening} but the previous row closed at "
                f"{previous_closing}: the balance does not carry across rows"
            )
        interest_sum += accrued
        previous_closing = closing

    assert interest_sum == Decimal(financials["interest_total"]), (
        f"rows sum to {interest_sum} but interest_total says "
        f"{financials['interest_total']} (section 11: totals equal the sum of rows)"
    )
    if first_from is not None:
        assert (
            rows[0]["from"] == first_from
        ), f"the ledger should start at {first_from}, it starts at {rows[0]['from']}"
    if last_to is not None:
        assert (
            rows[-1]["to"] == last_to
        ), f"the ledger should end at {last_to}, it ends at {rows[-1]['to']}"
    return interest_sum
