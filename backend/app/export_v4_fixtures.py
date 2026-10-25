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

What is **not** authoritative: every Option 1 (financing) number â€” discount, fee,
net amount, rate band, platform fee â€” is a hand-computed placeholder because
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
from backend.workflow.transitions import available_actions as workflow_available_actions
from backend.finance import (
    CaseFacts,
    FinanceConfig,
    bid_quote,
    compare_options,
    finance_config,
    round_money,
)

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


def build_events(disbursed_net: str) -> list[Event]:
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
            {"bid_id": "MOCK-BID-B", "financier_alias": "Financier B"},
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
        ("financing.disbursed", {"net_amount": disbursed_net}, EventActor.SYSTEM, datetime(2026, 10, 25, 9, 18, 45, tzinfo=UTC)),
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


# The action table lives in `backend/workflow/transitions.py` so the routes and the
# fixtures cannot drift apart; this module only reads it.

TERMINAL = {TrackState.BUYER_DECLINED, TrackState.NO_BIDS}


# ----------------------------------------------------------------- bids ----


def build_bids(cfg: FinanceConfig) -> list[Bid]:
    """Three fictional financiers, priced by `backend/finance` (never by a mock).

    Rates are the configured illustrative band, not market data. Financier C quotes
    the band midpoint so the three cards differ.
    """
    tenor_days = (DUE_DATE - AS_OF_IN_TIME).days
    midpoint = (cfg.rate_band_low + cfg.rate_band_high) / Decimal(2)
    rows = [
        ("MOCK-BID-A", "Financier A", cfg.rate_band_high),
        ("MOCK-BID-B", "Financier B", cfg.rate_band_low),
        ("MOCK-BID-C", "Financier C", midpoint),
    ]
    selected = "MOCK-BID-B"  # the best net: the owner takes the top of the sorted list
    bids = []
    for bid_id, alias, rate in rows:
        quote = bid_quote(ACCEPTED_AMOUNT, rate, tenor_days, cfg)
        bids.append(
            Bid(
                id=bid_id,
                track_id="TRK-FIN-0001",
                financier_alias=alias,
                annual_rate=round_money(rate),
                discount=quote["discount"],
                fee=quote["fee"],
                net_amount=quote["net_amount"],
                valid_until=datetime(2026, 10, 26, 9, 14, 10, tzinfo=UTC),
                status=BidStatus.SELECTED if bid_id == selected else BidStatus.AVAILABLE,
            )
        )
    return bids


# -------------------------------------------------------------- options ----


def engine_at(moment: date) -> Any:
    """The frozen engine's answer for the demo case at `moment`."""
    return evaluate_case(StatuteConfig.from_dict(load_config()), build_case_request(moment))


def build_options(cfg: FinanceConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    """Both cards, built by `backend.finance.compare_options`.

    Interest comes from the frozen engine through `interest_to_date`, so Option 2
    shows the engine's own figure rather than a second implementation of s.16.
    """

    def interest_to_date(moment: date) -> Decimal:
        financials = engine_at(moment).financials
        if financials is None:  # pragma: no cover - the demo case always evaluates
            raise RuntimeError("the demo case must evaluate for fixtures to be built")
        return financials.interest_total

    in_time = compare_options(
        engine_at(AS_OF_IN_TIME),
        CaseFacts(
            case_id=CASE_ID,
            accepted_amount=ACCEPTED_AMOUNT,
            due_date=DUE_DATE,
            recovery_state="STAGE_1_PREPARED",
        ),
        EXPECTED_IN_TIME,
        interest_to_date,
        cfg,
        as_of=AS_OF_IN_TIME,
    )
    overdue = compare_options(
        engine_at(AS_OF_OVERDUE),
        CaseFacts(
            case_id=CASE_ID,
            accepted_amount=ACCEPTED_AMOUNT,
            due_date=DUE_DATE,
            recovery_state="STAGE_2_PREPARED",
        ),
        EXPECTED_OVERDUE,
        interest_to_date,
        cfg,
        as_of=AS_OF_OVERDUE,
    )
    return in_time, overdue


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
    cfg = finance_config(load_config())
    bids = build_bids(cfg)
    selected = next(bid for bid in bids if bid.status == BidStatus.SELECTED)
    events = build_events(str(selected.net_amount))
    chain = verify_chain(events)
    if not chain.valid:  # pragma: no cover - a broken chain must never ship
        raise RuntimeError(f"event chain does not verify: first bad seq {chain.first_bad_seq}")

    tenor_days = (DUE_DATE - AS_OF_IN_TIME).days
    why_financing = (
        "Every Option 1 figure is computed by backend/finance (discount, fee, net) from the "
        "configured illustrative rate band and platform fee; the tenor is as_of to the due date. "
        "Option 2 figures are real engine output at the stated expected_payment_date. "
        "The rates are illustrative config, not market data; the arithmetic is not a placeholder."
    )

    financeable, not_financeable = build_options(cfg)
    dump(
        "options-financeable.json",
        wrap(
            "OptionsResponse",
            financeable,
            placeholder=False,
            placeholder_fields=[],
            why=why_financing,
        ),
    )
    dump(
        "options-not-financeable-overdue.json",
        wrap(
            "OptionsResponse",
            not_financeable,
            placeholder=False,
            placeholder_fields=[],
            why=why_financing
            + " Option 1 is unavailable because the invoice is past its due date "
            "(financing.max_overdue_days = 0, OQ-11); financeability supplies the reasons.",
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
            available_actions=workflow_available_actions(state.value, "FINANCING"),
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
            [b.model_dump(mode="json") for b in bids],
            placeholder=False,
            placeholder_fields=[],
            why=why_financing
            + " Each bid's discount, fee and net come from backend/finance.bid_quote; the mock "
            "only picks rates.",
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
        amount=selected.net_amount,
        currency="INR",
        utr="MOCKUTR2026102500007",
        settled_at=datetime(2026, 10, 25, 9, 18, 44, tzinfo=UTC),
    )
    dump(
        "payout.json",
        wrap(
            "PayoutStatus",
            payout.model_dump(mode="json"),
            placeholder=False,
            placeholder_fields=[],
            why=(
                "Disbursement of the selected bid "
                f"({selected.financier_alias}, net {selected.net_amount}), computed by "
                "backend/finance. The MOCK-prefixed UTR can never be mistaken for a real "
                "reference (golden rule 16)."
            ),
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
