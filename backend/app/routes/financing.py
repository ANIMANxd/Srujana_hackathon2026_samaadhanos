"""Financing track routes (architecture_v4 sections 5.1, 5.3 and 9).

Every mutating route enforces the three rules from section 8, in this order:

1. `Idempotency-Key` present (missing -> 400). A replay with the same body returns
   the stored response; the same key with a different body is a 409.
2. `If-Match: <track.version>` present (missing -> 400). A stale version is a 409 that
   hands back the **current CaseDetail**, so the client can re-render instead of
   guessing.
3. The transition itself. An event that the state machine does not allow is a 409
   with `INVALID_TRANSITION`, the current state and the events that *are* allowed.

`If-Match: 0` means "no track exists yet" on the create call: a creation precondition
is still a precondition, and it makes the header uniform across the four mutations.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlmodel import select

from backend.app import deps
from backend.app.routes import cases as case_routes
from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.app.schemas_v4 import (
    Bid,
    CaseDetail,
    ConsentDocument,
    ESignSession,
    FinanceabilityReason,
    FinancingActionResponse,
    Track as ContractTrack,
    TrackKind,
    TrackState,
)
from backend.artifacts.financing_consent import ConsentInputs, build_consent_markdown
from backend.artifacts.pdf import render_pdf
from backend.finance import CaseFacts, financeability
from backend.finance.config import finance_config
from backend.ports.errors import ProviderUnavailable
from backend.store import idempotency
from backend.store.db import session_scope
from backend.store.models import Case as CaseRow
from backend.store.models import FinancingRequest as FinancingRequestRow
from backend.workflow import financing_sm, tracks
from backend.workflow.transitions import available_actions

router = APIRouter(prefix="/api/v1", tags=["financing"])

ROUTE_START = "POST /api/v1/cases/{id}/financing"
ROUTE_ACCEPTANCE = "POST /api/v1/cases/{id}/financing/buyer-acceptance"
ROUTE_SELECT = "POST /api/v1/cases/{id}/financing/bids/{bid_id}/select"
ROUTE_CANCEL = "POST /api/v1/cases/{id}/financing/cancel"

LOCKED_RECOVERY_MESSAGE = "This invoice is financed; recovery actions are locked."


# ---------------------------------------------------------------- errors ----


def _fail(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _why_no_recommendation() -> None:  # pragma: no cover - documentation anchor
    """Golden rule 20: this module may never return a recommendation. Doing so is a bug."""


# ------------------------------------------------------------- preconditions ----


def _require_idempotency(key: str | None) -> str | JSONResponse:
    if not key:
        return _fail(
            400,
            "MISSING_IDEMPOTENCY_KEY",
            "This action needs an Idempotency-Key header so a retry cannot apply it twice.",
        )
    return key


def _require_if_match(value: str | None) -> int | JSONResponse:
    if value is None or value.strip() == "":
        return _fail(
            400,
            "MISSING_IF_MATCH",
            "This action needs an If-Match header carrying the track version "
            "(send 0 when the case has no track yet).",
        )
    try:
        return int(value.strip().strip('"'))
    except ValueError:
        return _fail(
            400,
            "MISSING_IF_MATCH",
            f"If-Match must be a track version number, got {value!r}.",
        )


def _replay_check(
    session, *, key: str, route: str, body: dict[str, Any]
) -> FinancingActionResponse | JSONResponse | None:
    """Return the stored response for a replay, a 409 for a changed body, else None."""
    existing = idempotency.lookup(session, key=key, route=route)
    if existing is None:
        return None
    digest = idempotency.hash_request(body)
    if existing.request_hash != digest:
        return _fail(
            409,
            "IDEMPOTENCY_CONFLICT",
            "This Idempotency-Key was already used for a different request. "
            "Use a new key for a new action.",
            {"key": key, "route": route},
        )
    return FinancingActionResponse.model_validate(existing.response_json)


def _record(session, *, key: str, route: str, body: dict[str, Any], response: dict[str, Any]) -> None:
    idempotency.store(
        session, key=key, route=route, request_hash=idempotency.hash_request(body), response=response
    )


def _stale(current, detail: CaseDetail | None = None) -> JSONResponse:
    details: dict[str, Any] = {
        "current_state": current.state,
        "current_version": current.version,
    }
    if detail is not None:
        # The task's requirement: a stale write hands back the current case, so the
        # client can re-render instead of guessing what changed.
        details["current"] = detail.model_dump(mode="json")
    return _fail(
        409,
        "STALE_VERSION",
        f"This case moved on: the track is now {current.state} at version "
        f"{current.version}. Re-read the case and try again.",
        details,
    )


def _invalid(state: TrackState, event: str, allowed: list[str], reason: str | None = None) -> JSONResponse:
    return _fail(
        409,
        "INVALID_TRANSITION",
        reason or f"The action {event!r} is not possible while the track is {state.value}.",
        {"state": state.value, "allowed_events": allowed},
    )


# ---------------------------------------------------------------- helpers ----


def _load(session, case_id: str):
    case = session.get(CaseRow, case_id)
    if case is None:
        return None
    return case


def _evaluation(session, case: CaseRow) -> CaseEvaluationResponse:
    row = case_routes._ensure_evaluation(session, case)
    return CaseEvaluationResponse.model_validate(row.response_json)


def _facts(case: CaseRow, evaluation: CaseEvaluationResponse, *, recovery_stage: int | None) -> CaseFacts:
    request = CaseEvaluationRequest.model_validate(case.input_json)
    due = evaluation.timeline.due_date if evaluation.timeline else request.transaction.invoice_date
    return CaseFacts(
        case_id=case.id,
        accepted_amount=Decimal(str(request.transaction.principal)),
        due_date=due,
        has_written_objection=any(obj.is_written for obj in request.objections),
        recovery_state=f"STAGE_{recovery_stage}_PREPARED" if recovery_stage else None,
    )


def _detail(session, case: CaseRow, track_row) -> CaseDetail:
    evaluation_row = case_routes._ensure_evaluation(session, case)
    state = TrackState(track_row.state) if track_row is not None else TrackState.NEW
    return CaseDetail(
        case=case_routes._case_contract(case),
        latest_evaluation=CaseEvaluationResponse.model_validate(evaluation_row.response_json),
        active_track=case_routes._track_contract(track_row),
        available_actions=available_actions(state, track_row.kind if track_row else None),
    )


def _response(session, case: CaseRow, track_row, **extra) -> FinancingActionResponse:
    return FinancingActionResponse(
        detail=_detail(session, case, track_row),
        track=case_routes._track_contract(track_row),
        **extra,
    )


def _adapters():
    return deps.get_adapters()


def _recovery_stage(session, case_id: str) -> int | None:
    from backend.store.models import Track as TrackRow

    row = session.exec(
        select(TrackRow).where(
            TrackRow.case_id == case_id, TrackRow.kind == "RECOVERY", TrackRow.closed_at.is_(None)
        )
    ).first()
    if row is None:
        return None
    from backend.workflow.recovery_sm import stage_number

    return stage_number(TrackState(row.state))


def _bids_from_provider(session, case: CaseRow) -> list[Bid]:
    """Ask the marketplace for bids. Returns [] when the provider is unavailable."""
    request = CaseEvaluationRequest.model_validate(case.input_json)
    marketplace = _adapters().marketplace
    try:
        ref = marketplace.register_invoice(
            __import__("backend.ports.marketplace", fromlist=["FactoringUnitIn"]).FactoringUnitIn(
                invoice_no=case.invoice_no,
                buyer_gstin=case.buyer_gstin,
                amount=case.accepted_amount,
                due_date=case.input_json["transaction"]["delivery_date"]
                and date.fromisoformat(case.input_json["transaction"]["delivery_date"]),
            ),
            idem_key=f"register:{case.id}",
        )
        return marketplace.list_bids(ref)
    except ProviderUnavailable:
        return []
    except Exception:  # noqa: BLE001 - the demo must not die on a mock outage
        return []


# ---------------------------------------------------------------- routes ----


@router.post("/cases/{case_id}/financing", response_model=FinancingActionResponse)
def start_financing(
    case_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Run financeability and open a financing track (Option 1).

    A `NOT_FINANCEABLE` outcome is a **200 with reasons**, not an error: the owner
    asked a question and gets an answer. Option 2 is untouched and still available.
    """
    key = _require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = _require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "start"}
    with session_scope() as session:
        case = _load(session, case_id)
        if case is None:
            return case_routes._not_found(case_id)

        replayed = _replay_check(session, key=key, route=ROUTE_START, body=body)
        if replayed is not None:
            return replayed

        evaluation = _evaluation(session, case)
        verdict = financeability(
            evaluation,
            _facts(case, evaluation, recovery_stage=_recovery_stage(session, case_id)),
            _recovery_stage(session, case_id),
            _adapters().clock.now().date(),
            finance_config(__import__("backend.app.config_loader", fromlist=["load_config"]).load_config()),
        )

        active = tracks.active_track(session, case_id)
        if active is not None:
            if TrackKind(active.kind) is TrackKind.FINANCING:
                # Order matters: "a track already exists" is more useful than "your
                # version is stale", and both are 409.
                return _fail(
                    409,
                    "TRACK_ALREADY_ACTIVE",
                    f"This case already has an open financing track ({active.state}).",
                    {
                        "state": active.state,
                        "current_version": active.version,
                        "allowed_events": financing_sm.allowed_events(TrackState(active.state)),
                    },
                )
            # A recovery track is open. Section 5.3 decides whether financing may start.
            decision = tracks.can_start(TrackKind.FINANCING, active, financeable=verdict["financeable"])
            if not decision.allowed:
                return _fail(
                    409,
                    decision.code or "TRACK_LOCKED",
                    decision.message or LOCKED_RECOVERY_MESSAGE,
                    {"state": active.state, "allowed_events": []},
                )
            # Allowed: pause recovery rather than deleting it, so "switch to Option 2"
            # can resume the stage it reached.
            if verdict["financeable"]:
                tracks.pause_track(session, active, reason="financing_started", actor="USER")
            else:
                return _fail(
                    409,
                    "TRACK_ALREADY_ACTIVE",
                    f"This case already has an open recovery track ({active.state}).",
                    {"state": active.state, "allowed_events": []},
                )
        elif version != 0:
            return _fail(
                409,
                "STALE_VERSION",
                "This case has no open track, so If-Match must be 0 to start one.",
                {"current_state": None, "current_version": 0},
            )

        track_row = tracks.open_track(
            session,
            case_id=case_id,
            kind=TrackKind.FINANCING,
            state=TrackState.NEW,
        )
        event = (
            financing_sm.FinancingEvent.CHECK_FINANCEABILITY
            if verdict["financeable"]
            else financing_sm.FinancingEvent.FINANCEABILITY_FAILED
        )
        track_row = tracks.apply_transition(
            session, track_row, event=event.value, expected_version=1, actor="USER"
        )

        reasons = [FinanceabilityReason(code=r["code"], message=r["message"]) for r in verdict["reasons"]]
        response = _response(session, case, track_row, reasons=reasons)
        _record(session, key=key, route=ROUTE_START, body=body, response=response.model_dump(mode="json"))
    return response


@router.post("/cases/{case_id}/financing/buyer-acceptance", response_model=FinancingActionResponse)
def request_buyer_acceptance(
    case_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Ask the buyer to accept the invoice, then follow the provider's decision.

    The buyer acts in their own login: nothing moves until they accept. This route
    applies `request_buyer_acceptance`, polls the provider once, and applies
    `buyer_accepted` when it has happened. The polling is a stand-in for the signed
    webhooks in `docs/webhooks.md`, which do not exist yet.
    """
    key = _require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = _require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "buyer_acceptance"}
    with session_scope() as session:
        case = _load(session, case_id)
        if case is None:
            return case_routes._not_found(case_id)
        replayed = _replay_check(session, key=key, route=ROUTE_ACCEPTANCE, body=body)
        if replayed is not None:
            return replayed

        track_row = tracks.active_track(session, case_id)
        state = TrackState(track_row.state) if track_row else TrackState.NEW
        if track_row is None or TrackKind(track_row.kind) is not TrackKind.FINANCING:
            return _invalid(state, "request_buyer_acceptance", ["start_financing"])
        if track_row.version != version:
            return _stale(track_row, _detail(session, case, track_row))

        warnings: list[FinanceabilityReason] = []
        marketplace = _adapters().marketplace
        request = CaseEvaluationRequest.model_validate(case.input_json)

        if state is TrackState.FINANCEABLE:
            from backend.ports.marketplace import FactoringUnitIn

            try:
                ref = marketplace.register_invoice(
                    FactoringUnitIn(
                        invoice_no=case.invoice_no,
                        buyer_gstin=case.buyer_gstin,
                        amount=case.accepted_amount,
                        due_date=date.fromisoformat(request.transaction.delivery_date.isoformat()),
                    ),
                    idem_key=f"register:{case.id}",
                )
                marketplace.request_buyer_acceptance(ref)
            except ProviderUnavailable:
                warnings.append(
                    FinanceabilityReason(
                        code="PROVIDER_UNAVAILABLE",
                        message=(
                            "The simulated marketplace is not reachable, so the buyer cannot "
                            "be asked right now. Your request has been recorded; try again "
                            "when the mock provider service is running."
                        ),
                    )
                )
                track_row = tracks.apply_transition(
                    session,
                    track_row,
                    event=financing_sm.FinancingEvent.REQUEST_BUYER_ACCEPTANCE.value,
                    expected_version=track_row.version,
                    actor="USER",
                )
                response = _response(session, case, track_row, reasons=warnings)
                _record(session, key=key, route=ROUTE_ACCEPTANCE, body=body, response=response.model_dump(mode="json"))
                return response

            track_row = tracks.apply_transition(
                session,
                track_row,
                event=financing_sm.FinancingEvent.REQUEST_BUYER_ACCEPTANCE.value,
                expected_version=track_row.version,
                actor="USER",
            )
            state = TrackState(track_row.state)

        if state is TrackState.AWAITING_BUYER_ACCEPTANCE:
            try:
                from backend.ports.marketplace import FactoringUnitIn

                ref = marketplace.register_invoice(
                    FactoringUnitIn(
                        invoice_no=case.invoice_no,
                        buyer_gstin=case.buyer_gstin,
                        amount=case.accepted_amount,
                        due_date=date.fromisoformat(request.transaction.delivery_date.isoformat()),
                    ),
                    idem_key=f"register:{case.id}",
                )
                acceptance = marketplace.get_acceptance(ref)
            except ProviderUnavailable:
                acceptance = None

            if acceptance is not None and acceptance.status.upper() == "ACCEPTED":
                track_row = tracks.apply_transition(
                    session,
                    track_row,
                    event=financing_sm.FinancingEvent.BUYER_ACCEPTED.value,
                    expected_version=track_row.version,
                    actor="PROVIDER_MOCK",
                )
                try:
                    ref = marketplace.register_invoice(
                        FactoringUnitIn(
                            invoice_no=case.invoice_no,
                            buyer_gstin=case.buyer_gstin,
                            amount=case.accepted_amount,
                            due_date=date.fromisoformat(request.transaction.delivery_date.isoformat()),
                        ),
                        idem_key=f"register:{case.id}",
                    )
                    marketplace.open_bidding(ref, timedelta(hours=24))
                except ProviderUnavailable:
                    pass
                state = TrackState(track_row.state)
            elif acceptance is not None and acceptance.status.upper() in {"REJECTED", "EXPIRED"}:
                event = (
                    financing_sm.FinancingEvent.BUYER_REJECTED
                    if acceptance.status.upper() == "REJECTED"
                    else financing_sm.FinancingEvent.WINDOW_EXPIRED
                )
                track_row = tracks.apply_transition(
                    session,
                    track_row,
                    event=event.value,
                    expected_version=track_row.version,
                    actor="PROVIDER_MOCK",
                )
                state = TrackState(track_row.state)

        if state is TrackState.BIDDING_OPEN:
            bids = _bids_from_provider(session, case)
            if bids:
                track_row = tracks.apply_transition(
                    session,
                    track_row,
                    event=financing_sm.FinancingEvent.BIDS_RECEIVED.value,
                    expected_version=track_row.version,
                    actor="PROVIDER_MOCK",
                    payload={"count": len(bids)},
                )

        response = _response(session, case, track_row, reasons=warnings)
        _record(session, key=key, route=ROUTE_ACCEPTANCE, body=body, response=response.model_dump(mode="json"))
    return response


@router.get("/cases/{case_id}/financing/bids", response_model=FinancingActionResponse)
def list_bids(case_id: str):
    """The bids received so far. A read: it never advances the state machine."""
    with session_scope() as session:
        case = _load(session, case_id)
        if case is None:
            return case_routes._not_found(case_id)
        track_row = tracks.active_track(session, case_id)
        if track_row is None:
            return _response(session, case, None, bids=[])
        state = TrackState(track_row.state)
        bids = _bids_from_provider(session, case) if state in {
            TrackState.BIDDING_OPEN,
            TrackState.BIDS_AVAILABLE,
        } else []
        return _response(session, case, track_row, bids=bids)


@router.post("/cases/{case_id}/financing/bids/{bid_id}/select", response_model=FinancingActionResponse)
def select_bid(
    case_id: str,
    bid_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Select a bid, sign the DEMO consent, and move to AWAITING_ESIGN.

    The consent document is built here, hashed, and its hash is what the eSign
    provider is asked to sign, so the signed copy can be checked against what was
    shown. The PDF is watermarked TEMPLATE and every party is fictional.
    """
    key = _require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = _require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "select_bid", "bid_id": bid_id}
    with session_scope() as session:
        case = _load(session, case_id)
        if case is None:
            return case_routes._not_found(case_id)
        replayed = _replay_check(session, key=key, route=ROUTE_SELECT, body=body)
        if replayed is not None:
            return replayed

        track_row = tracks.active_track(session, case_id)
        if track_row is None:
            return _invalid(TrackState.NEW, "select_bid", ["start_financing"])
        if track_row.version != version:
            return _stale(track_row, _detail(session, case, track_row))

        state = TrackState(track_row.state)
        if state is not TrackState.BIDS_AVAILABLE:
            return _invalid(state, "select_bid", financing_sm.allowed_events(state))

        bids = _bids_from_provider(session, case)
        bid = next((candidate for candidate in bids if candidate.id == bid_id), None)
        if bid is None:
            return _fail(
                404,
                "BID_NOT_FOUND",
                f"No bid {bid_id!r} is available on this case any more.",
                {"state": state.value},
            )

        now = _adapters().clock.now()
        try:
            track_row = tracks.apply_transition(
                session,
                track_row,
                event=financing_sm.FinancingEvent.SELECT_BID.value,
                expected_version=track_row.version,
                actor="USER",
                payload={"bid_id": bid.id, "financier_alias": bid.financier_alias},
                guard_context=financing_sm.GuardContext(now=now, bid_valid_until=bid.valid_until),
            )
        except tracks.StaleVersion as exc:
            # The other tab won the race between our version check and the UPDATE.
            return _stale(exc.current, _detail(session, case, exc.current))
        except tracks.InvalidStep as exc:
            return _invalid(exc.state, exc.event, exc.allowed, str(exc))

        request = CaseEvaluationRequest.model_validate(case.input_json)
        consent = ConsentInputs(
            case_id=case.id,
            invoice_no=case.invoice_no,
            supplier_name=request.supplier.name,
            buyer_name=request.buyer.name,
            financier_alias=bid.financier_alias,
            accepted_amount=case.accepted_amount,
            annual_rate=bid.annual_rate,
            discount=bid.discount,
            fee=bid.fee,
            net_amount=bid.net_amount,
            tenor_days=int((bid.valid_until.date() - now.date()).days),
            due_date=(request.transaction.delivery_date or request.transaction.invoice_date).isoformat(),
            bid_id=bid.id,
            esign_session_id="pending",
        )
        markdown = build_consent_markdown(consent)
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        pdf_base64 = None
        try:
            import base64

            pdf_bytes = render_pdf(
                markdown, title="Financing request and assignment consent (DEMO TEMPLATE)", case_id=case.id
            )
            pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
        except Exception:  # noqa: BLE001 - the markdown draft is complete without a PDF
            pdf_base64 = None

        from backend.ports.esign import SignableDoc, SignerRef

        document = SignableDoc(
            doc_id=f"CONSENT-{case.id}",
            doc_sha256=digest,
            title="Financing request and assignment consent (DEMO TEMPLATE)",
        )
        signer = SignerRef(display_name=request.supplier.name)
        try:
            session_model: ESignSession | None = _adapters().esign.create_session(
                document, signer, idem_key=f"esign:{case.id}:{bid.id}"
            )
        except ProviderUnavailable:
            session_model = None
        except NotImplementedError:
            session_model = None

        financing_row = session.exec(
            select(FinancingRequestRow).where(FinancingRequestRow.track_id == track_row.id)
        ).first()
        if financing_row is None:
            financing_row = FinancingRequestRow(
                track_id=track_row.id,
                accepted_amount=case.accepted_amount,
                tenor_days=consent.tenor_days,
                due_date=date.fromisoformat(consent.due_date),
                buyer_acceptance_status="ACCEPTED",
                selected_bid_id=bid.id,
                esign_session_id=session_model.session_id if session_model else None,
            )
            session.add(financing_row)
        else:
            financing_row.selected_bid_id = bid.id
            financing_row.esign_session_id = session_model.session_id if session_model else None
        session.flush()

        consent_doc = ConsentDocument(
            filename=f"{case.id}_financing_consent.pdf",
            sha256=digest,
            watermark="TEMPLATE",
            pdf_base64=pdf_base64,
        )
        if session_model is None:
            warnings = [
                FinanceabilityReason(
                    code="ESIGN_UNAVAILABLE",
                    message=(
                        "The DEMO signing session could not be created because the mock "
                        "provider service is not reachable. The consent document is ready."
                    ),
                )
            ]
        else:
            warnings = []

        response = _response(
            session, case, track_row, reasons=warnings, esign_session=session_model, consent_document=consent_doc
        )
        _record(session, key=key, route=ROUTE_SELECT, body=body, response=response.model_dump(mode="json"))
    return response


@router.post("/cases/{case_id}/financing/cancel", response_model=FinancingActionResponse)
def cancel_financing(
    case_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Cancel before signature. After signature the receivable is the financier's."""
    key = _require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = _require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "cancel"}
    with session_scope() as session:
        case = _load(session, case_id)
        if case is None:
            return case_routes._not_found(case_id)
        replayed = _replay_check(session, key=key, route=ROUTE_CANCEL, body=body)
        if replayed is not None:
            return replayed

        track_row = tracks.active_track(session, case_id)
        if track_row is None:
            return _invalid(TrackState.NEW, "user_cancel", ["start_financing"])
        if track_row.version != version:
            return _stale(track_row, _detail(session, case, track_row))

        try:
            track_row = tracks.apply_transition(
                session,
                track_row,
                event=financing_sm.FinancingEvent.USER_CANCEL.value,
                expected_version=track_row.version,
                actor="USER",
            )
        except tracks.StaleVersion as exc:
            return _stale(exc.current, _detail(session, case, exc.current))
        except tracks.InvalidStep as exc:
            return _invalid(exc.state, exc.event, exc.allowed, str(exc))

        response = _response(session, case, track_row)
        _record(session, key=key, route=ROUTE_CANCEL, body=body, response=response.model_dump(mode="json"))
    return response
