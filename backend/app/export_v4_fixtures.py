"""Generate the contract v1.1 example fixtures into `contracts/fixtures/v4/`.

Run: python -m backend.app.export_v4_fixtures

Why a generator instead of hand-written JSON:

- the eight financing states must describe **one** case, so they are built from a
  single `Case` object and cannot drift apart;
- the audit `Event` list must carry a **valid hash chain**, which means computing
  `sha256(prev_hash || canonical_json(type, payload, actor, created_at))` rather
  than typing 64-hex strings by hand;
- the two `OptionsResponse` fixtures carry Option 2 figures that are **engine
  output**, so they are read from `engine.evaluate.evaluate_case` at the two
  dates the cards describe (golden rule 7: every on-screen number comes from the
  engine).

What is **not** authoritative: every Option 1 (financing) number — discount, fee,
net amount, rate band, platform fee — is a hand-computed placeholder because
`backend/finance/` (B2) does not exist yet. Each file carries
`_fixture.placeholder: true` and names the placeholder fields (golden rule 7).
Regenerate with this module once B2 lands; do not hand-edit the JSON.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from backend.app.config_loader import load_config
from backend.app.schemas import CaseEvaluationRequest
from backend.app.schemas_v4 import (
    Bid,
    BidStatus,
    Case,
    CaseDetail,
    ChainVerifyResult,
    ESignSession,
    ESignStatus,
    Event,
    EventActor,
    BuyerAcceptanceStatus,
    FinancingRequest,
    OptionsResponse,
    PayoutState,
    PayoutStatus,
    Track,
    TrackKind,
    TrackState,
    WebhookDelivery,
    WebhookOutcome,
)
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case

OUT = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "v4"

# The demo case. Synthetic throughout (golden rule 11): no real party, GSTIN,
# phone or Udyam number. INV-0042 and 12,50,000 are the figures the v4
# architecture's example payload uses, so the docs and the fixtures agree.
CASE_ID = "01JAV4E7K3M9Q2R5T8V0W1XCZD"
INVOICE_NO = "INV-0042"
ACCEPTED_AMOUNT = Decimal("1250000.00")
INVOICE_DATE = date(2026, 9, 16)
DELIVERY_DATE = date(2026, 9, 14)
DUE_DATE = date(2026, 10, 29)  # delivery + the 45-day cap
CREDIT_DAYS = 45
TENOR_DAYS = 30
RATE_BAND = (Decimal("8.00"), Decimal("12.00"))
PLATFORM_FEE_PCT = Decimal("0.10")

ENGINE_VERSION = "1.0"
CONFIG_VERSION = "1.0"

# Two dates the cards describe: before the due date, and after it (OQ-11 keeps
# financing to the pre-due window, so the overdue case is not financeable).
AS_OF_IN_TIME = date(2026, 10, 25)
AS_OF_OVERDUE = date(2026, 11, 2)
EXPECTED_IN_TIME = date(2026, 11, 24)
EXPECTED_OVERDUE = date(2026, 12, 2)

GENESIS_HASH = "0" * 64


# ------------------------------------------------------------- helpers ----


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def discount_for(amount: Decimal, annual_rate_pct: Decimal, tenor_days: int) -> Decimal:
    """Simple, upfront discount (architecture_v4 section 1.1).

    Placeholder until `backend/finance/` owns this. Real money avoid: this is the
    documented formula, not a market rate.
    """
    raw = amount * (annual_rate_pct / Decimal(100)) * Decimal(tenor_days) / Decimal(365)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, etype: str, payload: dict[str, Any], actor: str, created: str) -> str:
    body = {"type": etype, "payload": payload, "actor": actor, "created_at": created}
    return hashlib.sha256((prev_hash + canonical(body)).encode("utf-8")).hexdigest()


# --------------------------------------------------------------- case ----


def build_case_request(calculation_date: date) -> CaseEvaluationRequest:
    return CaseEvaluationRequest.model_validate(
        {
            "contract_version": "1.0",
            "case_id": CASE_ID,
            "supplier": {
                "name": "Sample Supplies Pvt Ltd (synthetic)",
                "udyam_number": "UDYAM-SYN-000000000",
                "enterprise_class": "SMALL",
                "activity": "MANUFACTURING",
                "nic_codes": ["25990"],
                "udyam_registration_date": "2023-06-01",
                "investment_cr": "1.20",
                "turnover_cr": "8.00",
            },
            "buyer": {
                "name": "Sample Buyer Corp (synthetic)",
                "gstin": "29SYN000000000Z1",
                "tax_rate_pct": "31.20",
                "cost_of_capital_pct": "12.00",
            },
            "transaction": {
                "contract_date": "2026-08-01",
                "supply_date": DELIVERY_DATE.isoformat(),
                "invoice_date": INVOICE_DATE.isoformat(),
                "delivery_date": DELIVERY_DATE.isoformat(),
                "principal": money(ACCEPTED_AMOUNT),
                "written_credit_days": CREDIT_DAYS,
                "calculation_date": calculation_date.isoformat(),
                "years_deferred": None,
            },
            "objections": [],
            "part_payments": [],
            "acknowledgments": [],
            "evidence": {
                "items": [
                    {"kind": "INVOICE", "present": True, "ref": INVOICE_NO},
                    {"kind": "PO", "present": True, "ref": "PO-7781"},
                    {"kind": "DELIVERY_PROOF", "present": True, "ref": None},
                ]
            },
            "config_overrides": None,
        }
    )


def engine_figures(calculation_date: date) -> tuple[Decimal, Decimal]:
    """(interest_total, total_claim) straight from the frozen engine."""
    cfg = StatuteConfig.from_dict(load_config())
    result = evaluate_case(cfg, build_case_request(calculation_date))
    financials = result.financials
    if financials is None:  # pragma: no cover - the demo case always evaluates
        raise RuntimeError("the v4 demo case must evaluate for fixtures to be built")
    return financials.interest_total, financials.total_claim


def build_case() -> Case:
    return Case(
        id=CASE_ID,
        supplier_ref="SUP-SYN-0001",
        buyer_gstin="29SYN000000000Z1",
        invoice_no=INVOICE_NO,
        invoice_date=INVOICE_DATE,
        accepted_amount=ACCEPTED_AMOUNT,
        delivery_date=DELIVERY_DATE,
        input_json=build_case_request(AS_OF_IN_TIME).model_dump(mode="json"),
        engine_version=ENGINE_VERSION,
        config_version=CONFIG_VERSION,
        created_at=datetime(2026, 10, 25, 9, 12, 4, tzinfo=UTC),
    )


# -------------------------------------------------------------- events ----


def build_events() -> list[Event]:
    """A chain that verifies: the happy path up to DISBURSED."""
    rows: list[tuple[str, dict[str, Any], EventActor, datetime]] = [
        ("case.created", {"invoice_no": INVOICE_NO}, EventActor.USER, datetime(2026, 10, 25, 9, 12, 4, tzinfo=UTC)),
        ("evaluation.stored", {"as_of": "2026-10-25"}, EventActor.SYSTEM, datetime(2026, 10, 25, 9, 12, 5, tzinfo=UTC)),
        ("track.created", {"kind": "FINANCING"}, EventActor.USER, datetime(2026, 10, 25, 9, 13, 10, tzinfo=UTC)),
        ("financing.financeable", {"reasons": []}, EventActor.SYSTEM, datetime(2026, 10, 25, 9, 13, 11, tzinfo=UTC)),
        (
            "financing.acceptance_requested",
            {"buyer_gstin": "29SYN000000000Z1"},
            EventActor.USER,
            datetime(2026, 10, 25, 9, 14, 2, tzinfo=UTC),
        ),
        (
            "webhook.fu.accepted",
            {"provider_event_id": "MOCK-EVT-0001"},
            EventActor.PROVIDER_MOCK,
            datetime(2026, 10, 25, 9, 14, 6, tzinfo=UTC),
        ),
        ("financing.bidding_opened", {"window_hours": 24}, EventActor.SYSTEM, datetime(2026, 10, 25, 9, 14, 7, tzinfo=UTC)),
        (
            "webhook.bids.available",
            {"provider_event_id": "MOCK-EVT-0002", "bids": 3},
            EventActor.PROVIDER_MOCK,
            datetime(2026, 10, 25, 9, 14, 10, tzinfo=UTC),
        ),
        (
            "financing.bid_selected",
            {"bid_id": "MOCK-BID-C", "financier_alias": "Financier C"},
            EventActor.USER,
            datetime(2026, 10, 25, 9, 16, 31, tzinfo=UTC),
        ),
        (
            "webhook.esign.completed",
            {"provider_event_id": "MOCK-EVT-0003", "session_id": "MOCK-ESIGN-0007"},
            EventActor.PROVIDER_MOCK,
            datetime(2026, 10, 25, 9, 18, 12, tzinfo=UTC),
        ),
        (
            "webhook.payout.processed",
            {"provider_event_id": "MOCK-EVT-0004", "payout_ref": "MOCK-PAYOUT-0007"},
            EventActor.PROVIDER_MOCK,
            datetime(2026, 10, 25, 9, 18, 44, tzinfo=UTC),
        ),
        ("financing.disbursed", {"net_amount": "1240530.82"}, EventActor.SYSTEM, datetime(2026, 10, 25, 9, 18, 45, tzinfo=UTC)),
    ]

    events: list[Event] = []
    prev = GENESIS_HASH
    for seq, (etype, payload, actor, created) in enumerate(rows, start=1):
        draft = Event(
            seq=seq,
            case_id=CASE_ID,
            track_id="TRK-FIN-0001" if seq >= 3 else None,
            type=etype,
            payload_json=payload,
            actor=actor,
            created_at=created,
            prev_hash=prev,
            hash="",
        )
        # Hash the timestamp exactly as it is serialized (Pydantic writes UTC as
        # "...Z"), otherwise the committed JSON would never re-verify.
        stamp = draft.model_dump(mode="json")["created_at"]
        digest = chain_hash(prev, etype, payload, actor.value, stamp)
        events.append(draft.model_copy(update={"hash": digest}))
        prev = digest
    return events


def verify_chain(events: list[Event]) -> ChainVerifyResult:
    """Recompute the chain exactly as `/events/verify` will (docs/webhooks.md)."""
    prev = GENESIS_HASH
    for event in events:
        expected = chain_hash(
            prev,
            event.type,
            event.payload_json,
            event.actor.value,
            event.model_dump(mode="json")["created_at"],
        )
        if expected != event.hash or event.prev_hash != prev:
            return ChainVerifyResult(valid=False, checked=event.seq - 1, first_bad_seq=event.seq)
        prev = event.hash
    return ChainVerifyResult(valid=True, checked=len(events), first_bad_seq=None)


# --------------------------------------------------------------- tracks ----


def build_track(state: TrackState, *, closed: bool = False) -> Track:
    return Track(
        id="TRK-FIN-0001",
        case_id=CASE_ID,
        kind=TrackKind.FINANCING,
        state=state,
        version=1,
        created_at=datetime(2026, 10, 25, 9, 13, 10, tzinfo=UTC),
        closed_at=datetime(2026, 10, 30, 11, 0, 0, tzinfo=UTC) if closed else None,
    )


# Actions the workflow allows from each state (docs/state-machines.md section 3).
# Recovery only appears while nothing is assigned to a financier.
ACTIONS: dict[TrackState, list[str]] = {
    TrackState.FINANCEABLE: ["request_buyer_acceptance", "switch_to_recovery", "cancel_financing"],
    TrackState.AWAITING_BUYER_ACCEPTANCE: ["wait_for_buyer", "switch_to_recovery", "cancel_financing"],
    TrackState.BIDS_AVAILABLE: ["select_bid", "cancel_financing"],
    TrackState.AWAITING_ESIGN: ["complete_esign", "cancel_financing"],
    TrackState.AWAITING_DISBURSEMENT: ["wait_for_payout"],
    TrackState.DISBURSED: ["view_events", "download_pack"],
    TrackState.BUYER_DECLINED: ["switch_to_recovery", "cancel_financing"],
    TrackState.NO_BIDS: ["switch_to_recovery", "cancel_financing"],
}

TERMINAL = {TrackState.BUYER_DECLINED, TrackState.NO_BIDS}


# ----------------------------------------------------------------- bids ----


def build_bids() -> list[Bid]:
    fee = (ACCEPTED_AMOUNT * (PLATFORM_FEE_PCT / Decimal(100))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    rows = [
        ("MOCK-BID-A", "Financier A", Decimal("12.00")),
        ("MOCK-BID-B", "Financier B", Decimal("8.00")),
        ("MOCK-BID-C", "Financier C", Decimal("10.25")),
    ]
    bids = []
    for bid_id, alias, rate in rows:
        discount = discount_for(ACCEPTED_AMOUNT, rate, TENOR_DAYS)
        bids.append(
            Bid(
                id=bid_id,
                track_id="TRK-FIN-0001",
                financier_alias=alias,
                annual_rate=rate,
                discount=discount,
                fee=fee,
                net_amount=ACCEPTED_AMOUNT - discount - fee,
                valid_until=datetime(2026, 10, 26, 9, 14, 10, tzinfo=UTC),
                status=BidStatus.SELECTED if bid_id == "MOCK-BID-C" else BidStatus.AVAILABLE,
            )
        )
    return bids


# -------------------------------------------------------------- options ----


def build_options() -> tuple[OptionsResponse, OptionsResponse]:
    low_rate, high_rate = RATE_BAND
    fee = (ACCEPTED_AMOUNT * (PLATFORM_FEE_PCT / Decimal(100))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    best_discount = discount_for(ACCEPTED_AMOUNT, low_rate, TENOR_DAYS)
    worst_discount = discount_for(ACCEPTED_AMOUNT, high_rate, TENOR_DAYS)

    def indicative() -> dict[str, Any]:
        return {
            "accepted_amount": money(ACCEPTED_AMOUNT),
            "tenor_days": TENOR_DAYS,
            "rate_band_pct": {"low": money(low_rate), "high": money(high_rate), "label": "illustrative"},
            "platform_fee_pct": money(PLATFORM_FEE_PCT),
            "net_receivable_range": {
                "low": money(ACCEPTED_AMOUNT - worst_discount - fee),
                "high": money(ACCEPTED_AMOUNT - best_discount - fee),
            },
            "settlement": "T+2 after bid acceptance (config: treds.settlement_days)",
        }

    in_time_interest, in_time_total = engine_figures(EXPECTED_IN_TIME)
    overdue_interest, overdue_total = engine_figures(EXPECTED_OVERDUE)

    financeable = OptionsResponse.model_validate(
        {
            "case_id": CASE_ID,
            "as_of": AS_OF_IN_TIME.isoformat(),
            "simulation": True,
            "get_paid_early": {
                "available": True,
                "unavailable_reasons": [],
                "indicative": indicative(),
                "notes": [
                    "Your buyer must accept the invoice on the platform first.",
                    "Interest accrued so far is not included.",
                ],
                "citations": [
                    {"source": "RBI TReDS guidelines (2014)", "ref": "config:treds.settlement_days"}
                ],
            },
            "recover_with_law": {
                "available": True,
                "expected_payment_date": EXPECTED_IN_TIME.isoformat(),
                "principal": money(ACCEPTED_AMOUNT),
                "interest_to_expected_date": money(in_time_interest),
                "total_if_paid": money(in_time_total),
                "current_stage": "STAGE_1_PREPARED",
                "notes": [
                    "Only received if the buyer pays.",
                    "You send every message yourself.",
                ],
                "citations": [
                    {"source": "MSMED Act s.16", "ref": "config:interest_multiplier"}
                ],
            },
            "recommendation": None,
        }
    )

    not_financeable = OptionsResponse.model_validate(
        {
            "case_id": CASE_ID,
            "as_of": AS_OF_OVERDUE.isoformat(),
            "simulation": True,
            "get_paid_early": {
                "available": False,
                "unavailable_reasons": [
                    "The due date has passed. This build only finances invoices before the due date.",
                    "Interest accrued before financing would not be covered.",
                ],
                "indicative": None,
                "notes": [
                    "Your buyer must accept the invoice on the platform first.",
                ],
                "citations": [],
            },
            "recover_with_law": {
                "available": True,
                "expected_payment_date": EXPECTED_OVERDUE.isoformat(),
                "principal": money(ACCEPTED_AMOUNT),
                "interest_to_expected_date": money(overdue_interest),
                "total_if_paid": money(overdue_total),
                "current_stage": "STAGE_2_PREPARED",
                "notes": [
                    f"Overdue since {DUE_DATE.isoformat()}.",
                    "Only received if the buyer pays.",
                    "You send every message yourself.",
                ],
                "citations": [
                    {"source": "MSMED Act s.16", "ref": "config:interest_multiplier"}
                ],
            },
            "recommendation": None,
        }
    )
    return financeable, not_financeable


# ---------------------------------------------------------------- write ----


def wrap(schema: str, payload: Any, *, placeholder: bool, placeholder_fields: list[str], why: str) -> dict:
    return {
        "_fixture": {
            "schema": schema,
            "contract_version": "1.1",
            "synthetic": True,
            "placeholder": placeholder,
            "placeholder_fields": placeholder_fields,
            "why": why,
            "regenerate_with": "python -m backend.app.export_v4_fixtures",
        },
        "payload": payload,
    }


def dump(name: str, obj: Any) -> None:
    path = OUT / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    case = build_case()
    events = build_events()
    chain = verify_chain(events)
    if not chain.valid:  # pragma: no cover - a broken chain must never ship
        raise RuntimeError(f"event chain does not verify: first bad seq {chain.first_bad_seq}")

    financing_numbers = [
        "get_paid_early.indicative.accepted_amount",
        "get_paid_early.indicative.rate_band_pct",
        "get_paid_early.indicative.platform_fee_pct",
        "get_paid_early.indicative.net_receivable_range",
    ]
    why_financing = (
        "Option 1 figures are hand-computed with the architecture_v4 section 1.1 formula "
        "(discount = amount*rate*tenor/365, net = amount-discount-fee) because backend/finance "
        "(B2) does not exist yet. Option 2 figures are real engine output at the stated "
        "expected_payment_date."
    )

    financeable, not_financeable = build_options()
    dump(
        "options-financeable.json",
        wrap(
            "OptionsResponse",
            financeable.model_dump(mode="json"),
            placeholder=True,
            placeholder_fields=financing_numbers,
            why=why_financing,
        ),
    )
    dump(
        "options-not-financeable-overdue.json",
        wrap(
            "OptionsResponse",
            not_financeable.model_dump(mode="json"),
            placeholder=True,
            placeholder_fields=financing_numbers + ["get_paid_early.available", "get_paid_early.unavailable_reasons"],
            why=why_financing + " Option 1 is unavailable because the invoice is past its due date "
            "(financing.max_overdue_days = 0, OQ-11).",
        ),
    )

    states = [
        TrackState.FINANCEABLE,
        TrackState.AWAITING_BUYER_ACCEPTANCE,
        TrackState.BIDS_AVAILABLE,
        TrackState.AWAITING_ESIGN,
        TrackState.AWAITING_DISBURSEMENT,
        TrackState.DISBURSED,
        TrackState.BUYER_DECLINED,
        TrackState.NO_BIDS,
    ]
    for state in states:
        detail = CaseDetail(
            case=case,
            latest_evaluation=evaluate_case(
                StatuteConfig.from_dict(load_config()), build_case_request(AS_OF_IN_TIME)
            ),
            active_track=build_track(state, closed=state in TERMINAL),
            available_actions=ACTIONS[state],
        )
        dump(
            f"case-detail-{state.value}.json",
            wrap(
                "CaseDetail",
                detail.model_dump(mode="json"),
                placeholder=False,
                placeholder_fields=[],
                why=(
                    "case + latest_evaluation are real engine output; the track state and "
                    "available_actions are the transition table from docs/state-machines.md. "
                    "No Option 1 money appears here, so nothing is a placeholder."
                ),
            ),
        )

    dump(
        "bids.json",
        wrap(
            "Bid[]",
            [b.model_dump(mode="json") for b in build_bids()],
            placeholder=True,
            placeholder_fields=["[].annual_rate", "[].discount", "[].fee", "[].net_amount"],
            why=why_financing + " Rates are the illustrative mock_financing.rate_band, not market data.",
        ),
    )

    esign = ESignSession(
        session_id="MOCK-ESIGN-0007",
        status=ESignStatus.SIGNED,
        signing_url="/mock/esign/MOCK-ESIGN-0007",
        expires_at=datetime(2026, 10, 25, 9, 28, 31, tzinfo=UTC),
        signed_doc_sha256="9f2c1b7d4e6a8c0b3d5f7a9c1e3b5d7f9a1c3e5b7d9f1a3c5e7b9d1f3a5c7e9b",
        signer_display="Demo Signer",
        signed_at=datetime(2026, 10, 25, 9, 18, 12, tzinfo=UTC),
    )
    dump(
        "esign-session.json",
        wrap(
            "ESignSession",
            esign.model_dump(mode="json"),
            placeholder=False,
            placeholder_fields=[],
            why="A simulated signing session. No Aadhaar field exists and none is stored "
            "(golden rule 18); the hash is a synthetic placeholder digest.",
        ),
    )

    payout = PayoutStatus(
        payout_ref="MOCK-PAYOUT-0007",
        status=PayoutState.PROCESSED,
        amount=ACCEPTED_AMOUNT - discount_for(ACCEPTED_AMOUNT, Decimal("10.25"), TENOR_DAYS)
        - (ACCEPTED_AMOUNT * (PLATFORM_FEE_PCT / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        currency="INR",
        utr="MOCKUTR2026102500007",
        settled_at=datetime(2026, 10, 25, 9, 18, 44, tzinfo=UTC),
    )
    dump(
        "payout.json",
        wrap(
            "PayoutStatus",
            payout.model_dump(mode="json"),
            placeholder=True,
            placeholder_fields=["amount"],
            why="Disbursement of the selected Financier C bid (net 12,38,219.18). The MOCK-prefixed "
            "UTR can never be mistaken for a real reference (golden rule 16).",
        ),
    )

    dump(
        "events.json",
        wrap(
            "Event[]",
            [e.model_dump(mode="json") for e in events],
            placeholder=False,
            placeholder_fields=[],
            why="An append-only, hash-chained audit trail that verifies. "
            "hash = sha256(prev_hash || canonical_json(type, payload, actor, created_at)); "
            f"the first event's prev_hash is {GENESIS_HASH[:8]}... (genesis). "
            "Tamper-evident, not tamper-proof.",
        ),
    )
    dump(
        "chain-verify-result.json",
        wrap(
            "ChainVerifyResult",
            chain.model_dump(mode="json"),
            placeholder=False,
            placeholder_fields=[],
            why="The result of recomputing the chain in events.json: every link checks out.",
        ),
    )

    deliveries = [
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0001",
            provider="marketplace",
            received_at=datetime(2026, 10, 25, 9, 14, 6, tzinfo=UTC),
            signature_ok=True,
            processed_at=datetime(2026, 10, 25, 9, 14, 6, tzinfo=UTC),
            outcome=WebhookOutcome.APPLIED,
        ),
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0002",
            provider="marketplace",
            received_at=datetime(2026, 10, 25, 9, 14, 10, tzinfo=UTC),
            signature_ok=True,
            processed_at=datetime(2026, 10, 25, 9, 14, 10, tzinfo=UTC),
            outcome=WebhookOutcome.APPLIED,
        ),
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0002",
            provider="marketplace",
            received_at=datetime(2026, 10, 25, 9, 14, 11, tzinfo=UTC),
            signature_ok=True,
            processed_at=None,
            outcome=WebhookOutcome.DUPLICATE,
        ),
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0003",
            provider="esign",
            received_at=datetime(2026, 10, 25, 9, 18, 12, tzinfo=UTC),
            signature_ok=True,
            processed_at=datetime(2026, 10, 25, 9, 18, 12, tzinfo=UTC),
            outcome=WebhookOutcome.APPLIED,
        ),
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0005",
            provider="disbursement",
            received_at=datetime(2026, 10, 25, 9, 18, 40, tzinfo=UTC),
            signature_ok=True,
            processed_at=None,
            outcome=WebhookOutcome.PARKED,
        ),
        WebhookDelivery(
            provider_event_id="MOCK-EVT-0006",
            provider="marketplace",
            received_at=datetime(2026, 10, 25, 9, 19, 2, tzinfo=UTC),
            signature_ok=False,
            processed_at=None,
            outcome=WebhookOutcome.REJECTED,
        ),
    ]
    dump(
        "webhook-deliveries.json",
        wrap(
            "WebhookDelivery[]",
            [d.model_dump(mode="json") for d in deliveries],
            placeholder=False,
            placeholder_fields=[],
            why="Every delivery is recorded, including the duplicate (no side effects), the "
            "out-of-order event parked until the state catches up, and the bad-signature "
            "rejection. See docs/webhooks.md.",
        ),
    )

    print(f"wrote {len(list(OUT.glob('*.json')))} fixtures to {OUT}")


if __name__ == "__main__":
    main()
