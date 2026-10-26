"""Case lifecycle routes (architecture_v4 section 9, contract v1.1).

The v1.0 surface is untouched: `POST /api/v1/evaluate-case` still answers statelessly
and keeps its exact response. These routes add the **stateful** option beside it, so
the extraction approve step can either keep posting evaluate-case or create a real
case and get an id, a track and an audit trail.

Two rules worth stating out loud:

- **The client never mints an id.** `POST /cases` issues a ULID and overwrites whatever
  `case_id` the body carried, so a case id is always server-issued.
- **`GET` may write.** Reading a case re-runs the engine when the clock's day has moved
  past the stored evaluation, and stores the new snapshot. That is what keeps the
  interest figures honest on a demo that spans days; it is deliberate, not a bug.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from sqlmodel import select

from backend.app import deps
from backend.app.config_loader import load_config
from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.app.schemas_v4 import (
    Case,
    CaseCreateRequest,
    CaseDetail,
    CaseListResponse,
    CaseSummary,
    ChainVerifyResult,
    Event as ContractEvent,
    EventActor,
    Track as ContractTrack,
    TrackKind,
    TrackState,
)
from backend.app.schemas_v5 import Payment, PaymentCreateRequest, PaymentListResponse
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case as evaluate_case_engine
from backend.store import audit, idempotency
from backend.store import customers as customer_book
from backend.store.db import session_scope
from backend.store.ids import new_ulid
from backend.store.models import Case as CaseRow
from backend.store.models import Evaluation as EvaluationRow
from backend.store.models import Event as EventRow
from backend.store.models import Payment as PaymentRow
from backend.store.models import Track as TrackRow
from backend.workflow import tracks as workflow_tracks
from backend.workflow.transitions import available_actions

router = APIRouter(prefix="/api/v1", tags=["cases"])

# Idempotency scope for the payment create route. The body includes the case id,
# so the same key used for a different case is a conflict, not a replay.
ROUTE_CREATE_PAYMENT = "POST /api/v1/cases/{id}/payments"

# A payment received after the receivable was assigned belongs to the financier.
# "DISBURSED or later" is the financing track's terminal side of the machine;
# DISBURSEMENT_FAILED is before any money reached the supplier, so it is not here.
FINANCED_STATES: frozenset[str] = frozenset(
    {
        TrackState.DISBURSED.value,
        TrackState.SETTLED.value,
        TrackState.SETTLED_WITHOUT_RECOURSE.value,
    }
)

PAYMENT_CAP_ASSUMPTION = (
    "The engine has no financials for this case, so the payment cap uses the "
    "invoice amount less recorded payments; accrued interest is unknown."
)


# ------------------------------------------------------------- helpers ----


def _engine(request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Run the frozen engine. The store never computes a legal number itself."""
    config = StatuteConfig.from_dict(load_config())
    return evaluate_case_engine(config, request)


def _request_from_input(input_json: dict[str, Any], calculation_date: date) -> CaseEvaluationRequest:
    """Rebuild the engine input for a new day.

    Only `calculation_date` moves: every other field is exactly what was stored, so
    the case cannot silently acquire a new fact on re-read.
    """
    payload = {**input_json, "transaction": {**input_json["transaction"]}}
    payload["transaction"]["calculation_date"] = calculation_date.isoformat()
    return CaseEvaluationRequest.model_validate(payload)


def _store_evaluation(
    session, case_id: str, response: CaseEvaluationResponse, as_of: date
) -> EvaluationRow:
    row = EvaluationRow(
        id=new_ulid(),
        case_id=case_id,
        as_of=as_of,
        response_json=response.model_dump(mode="json"),
        engine_version="1.0",
        config_hash=deps.config_version(),
    )
    session.add(row)
    session.flush()
    return row


def _latest_evaluation(session, case_id: str) -> EvaluationRow | None:
    return session.exec(
        select(EvaluationRow)
        .where(EvaluationRow.case_id == case_id)
        .order_by(EvaluationRow.as_of.desc(), EvaluationRow.created_at.desc())
        .limit(1)
    ).first()


def _ensure_evaluation(session, case: CaseRow) -> EvaluationRow:
    """Return today's evaluation, re-running the engine if the stored one is stale.

    A stored snapshot from an earlier day is not wrong, but the money it shows is
    not today's money: s.16 interest accrues daily. Re-evaluating on read keeps the
    screen truthful and leaves an immutable trail of every snapshot it passed
    through.
    """
    today = deps.get_adapters().clock.now().date()
    latest = _latest_evaluation(session, case.id)
    input_json = dict(case.input_json)
    if latest is None or latest.as_of != today:
        request = _request_from_input(input_json, today)
        response = _engine(request)
        latest = _store_evaluation(session, case.id, response, today)
    return latest


def _case_contract(row: CaseRow) -> Case:
    return Case.model_validate(
        {
            "id": row.id,
            "supplier_ref": row.supplier_ref,
            "buyer_gstin": row.buyer_gstin,
            "invoice_no": row.invoice_no,
            "invoice_date": row.invoice_date,
            "accepted_amount": row.accepted_amount,
            "delivery_date": row.delivery_date,
            "input_json": row.input_json,
            "engine_version": row.engine_version,
            "config_version": row.config_version,
            "created_at": row.created_at,
        }
    )


def _track_contract(row: TrackRow | None) -> ContractTrack | None:
    if row is None:
        return None
    return ContractTrack.model_validate(
        {
            "id": row.id,
            "case_id": row.case_id,
            "kind": row.kind,
            "state": row.state,
            "version": row.version,
            "created_at": row.created_at,
            "closed_at": row.closed_at,
        }
    )


def _active_track(session, case_id: str) -> TrackRow | None:
    return session.exec(
        select(TrackRow).where(TrackRow.case_id == case_id, TrackRow.closed_at.is_(None))
    ).first()


def _event_contract(row: EventRow) -> ContractEvent:
    return ContractEvent.model_validate(
        {
            "seq": row.seq,
            "case_id": row.case_id,
            "track_id": row.track_id,
            "type": row.type,
            "payload_json": row.payload_json,
            "actor": EventActor(row.actor),
            "created_at": row.created_at,
            "prev_hash": row.prev_hash,
            "hash": row.hash,
        }
    )


def _stage_from_state(state: TrackState) -> int | None:
    """The recovery stage a track state names, if it names one."""
    if state.value.startswith("STAGE_"):
        head = state.value.split("_")[1]
        return int(head) if head.isdigit() else None
    return None


def _detail(session, case: CaseRow, evaluation: EvaluationRow) -> CaseDetail:
    track = _active_track(session, case.id)
    state = TrackState(track.state) if track is not None else TrackState.NEW
    response = CaseEvaluationResponse.model_validate(evaluation.response_json)
    return CaseDetail(
        case=_case_contract(case),
        latest_evaluation=response,
        active_track=_track_contract(track),
        available_actions=available_actions(state, track.kind if track else None),
    )


def _not_found(case_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No case with id {case_id!r}")


# ------------------------------------------------------------ payments ----
# The engine already has a payment input (`transaction.part_payments`), so a
# recorded payment is appended there and the case is re-evaluated through the
# frozen engine. The v5 `payments` row remains the source of truth for the
# audit trail; the engine input carries a `v5:<payment_id>` reference so a void
# can remove exactly that entry without guessing by amount/date.


def _financing_track(session, case_id: str) -> TrackRow | None:
    """The latest financing track, open or closed, for the payment 409 guard."""
    return session.exec(
        select(TrackRow)
        .where(
            TrackRow.case_id == case_id,
            TrackRow.kind == TrackKind.FINANCING.value,
        )
        .order_by(TrackRow.created_at.desc(), TrackRow.id.desc())
    ).first()


def _financed_error(session, case_id: str) -> HTTPException | None:
    track = _financing_track(session, case_id)
    if track is not None and track.state in FINANCED_STATES:
        return HTTPException(
            status_code=409,
            detail="This invoice is financed; the buyer pays the financier.",
        )
    return None


def _payment_contract(row: PaymentRow) -> Payment:
    return Payment.model_validate(
        {
            "id": row.id,
            "case_id": row.case_id,
            "amount": row.amount,
            "paid_on": row.paid_on,
            "method": row.method,
            "note": row.note,
            "created_at": row.created_at,
            "voided_at": row.voided_at,
        }
    )


def _remaining_claim(
    session, case: CaseRow, evaluation: EvaluationRow
) -> tuple[Decimal, str | None, str]:
    """Remaining claim, a fallback assumption, and which basis was used.

    The engine's `total_claim` already includes principal, accrued interest and
    every payment in `input_json`. It is the only figure the cap may use; this
    module never recomputes interest. Only when the engine has no financials
    (an ineligible/blocked case) does it fall back to invoice amount minus
    recorded payments, and it returns an assumption the route records.
    """
    response = CaseEvaluationResponse.model_validate(evaluation.response_json)
    if response.financials is not None:
        claim = Decimal(str(response.financials.total_claim))
        return max(claim, Decimal("0.00")), None, "engine_total_claim"

    paid = sum(
        (
            payment.amount
            for payment in customer_book.payments_for_case(
                session, case.id, include_voided=False
            )
        ),
        Decimal("0.00"),
    )
    remaining = max(case.accepted_amount - paid, Decimal("0.00"))
    return remaining, PAYMENT_CAP_ASSUMPTION, "principal_fallback"


def _add_payment_to_engine_input(session, case: CaseRow, payment: PaymentRow) -> None:
    payload = dict(case.input_json)
    part_payments = list(payload.get("part_payments") or [])
    part_payments.append(
        {
            "date": payment.paid_on.isoformat(),
            "amount": format(payment.amount, "f"),
            "reference": f"v5:{payment.id}",
        }
    )
    payload["part_payments"] = part_payments
    case.input_json = payload
    session.add(case)
    session.flush()


def _remove_payment_from_engine_input(session, case: CaseRow, payment_id: str) -> None:
    payload = dict(case.input_json)
    reference = f"v5:{payment_id}"
    entries = list(payload.get("part_payments") or [])
    payload["part_payments"] = [
        entry
        for entry in entries
        if not (isinstance(entry, dict) and entry.get("reference") == reference)
    ]
    case.input_json = payload
    session.add(case)
    session.flush()


def _reevaluate(session, case: CaseRow) -> EvaluationRow:
    """Force a new engine snapshot after the payment input changed.

    `_ensure_evaluation` is deliberately not used here: it returns today's
    snapshot when one exists, which would be the *pre-payment* snapshot.
    """
    today = deps.get_adapters().clock.now().date()
    request = _request_from_input(dict(case.input_json), today)
    response = _engine(request)
    return _store_evaluation(session, case.id, response, today)


def _close_recovery_if_paid(
    session,
    case: CaseRow,
    payment: PaymentRow,
    evaluation: EvaluationRow,
    *,
    actor: str,
) -> None:
    """Close an open recovery track as PAID once the claim is fully paid.

    A payment can arrive at any ladder stage, so `tracks.close_recovery_as_paid`
    is a payment-driven terminal close rather than the user's post-ODR
    `mark_paid` event. The audit trail records the payment id and the basis.
    """
    remaining, assumption, basis = _remaining_claim(session, case, evaluation)
    if assumption is not None:
        audit.append_event(
            session,
            case_id=case.id,
            type="payment.assumption",
            payload={"payment_id": payment.id, "assumption": assumption},
            actor=actor,
        )
    if remaining > 0:
        return

    recovery = session.exec(
        select(TrackRow).where(
            TrackRow.case_id == case.id,
            TrackRow.kind == TrackKind.RECOVERY.value,
            TrackRow.closed_at.is_(None),
        )
    ).first()
    if recovery is None:
        return
    workflow_tracks.close_recovery_as_paid(
        session,
        recovery,
        payment_id=payment.id,
        total_claim=format(remaining, "f") if basis == "engine_total_claim" else None,
        basis=basis,
        actor=actor,
    )


# -------------------------------------------------------------- routes ----


@router.post("/cases", response_model=CaseDetail, status_code=201)
def create_case(
    payload: CaseCreateRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CaseDetail:
    """Create a case from approved fields, evaluate it, and open its audit trail.

    The client's `case_id` is replaced by a server-issued ULID: an id that a client
    can choose is an id a client can collide with or forge.

    `buyer_contact` is accepted so the caller can draft the acceptance invite, and is
    **not stored** — there is no column for it in the architecture_v4 section 4
    schema, and persisting personal data needs a DPDP decision the repo has not
    taken. No phone number or email is logged.
    """
    request = payload.model_copy(update={"case_id": new_ulid()})
    engine_request = CaseEvaluationRequest.model_validate(request.model_dump(mode="json"))
    engine_response = _engine(engine_request)

    with session_scope() as session:
        case = CaseRow(
            id=engine_request.case_id,
            supplier_ref=engine_request.supplier.udyam_number or engine_request.supplier.name,
            buyer_gstin=engine_request.buyer.gstin,
            invoice_no=_invoice_no(engine_request),
            invoice_date=engine_request.transaction.invoice_date,
            accepted_amount=engine_request.transaction.principal,
            delivery_date=engine_request.transaction.delivery_date,
            input_json=engine_request.model_dump(mode="json"),
            engine_version="1.0",
            config_version=deps.config_version(),
        )
        session.add(case)
        session.flush()

        _store_evaluation(
            session, case.id, engine_response, engine_request.transaction.calculation_date
        )
        audit.append_event(
            session,
            case_id=case.id,
            type="case.created",
            payload={"invoice_no": case.invoice_no, "source": "api.cases.create"},
            actor=EventActor.USER.value,
            created_at=case.created_at,
        )
        # Customer identity is decided by the pure resolver in
        # backend/insights/identity.py; the store applies it and persists the
        # buyer's GSTIN under that customer. This runs after case.created so the
        # chain always opens with the case itself.
        customer_book.attach_case_to_customer(
            session,
            case,
            at=case.created_at,
            source="api.cases.create",
            actor=EventActor.USER.value,
        )

        evaluation = _latest_evaluation(session, case.id)
        assert evaluation is not None
        detail = _detail(session, case, evaluation)

    response.headers["Location"] = f"/api/v1/cases/{detail.case.id}"
    if idempotency_key:
        # Recorded for traceability only. /cases is not in the section 8 list that
        # requires the header; the financing and recovery routes will enforce it.
        response.headers["Idempotency-Key"] = idempotency_key
    return detail


@router.get("/cases", response_model=CaseListResponse)
def list_cases(limit: int = Query(default=100, ge=1, le=500)) -> CaseListResponse:
    """Every case, with the figures the Dues home shows.

    Reading may create an evaluation per case (see `_ensure_evaluation`), so the
    first call after midnight is the expensive one.
    """
    with session_scope() as session:
        rows = session.exec(select(CaseRow).order_by(CaseRow.created_at.desc()).limit(limit)).all()
        summaries = [_summary(session, case) for case in rows]
    return CaseListResponse(cases=summaries, count=len(summaries))


@router.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(case_id: str) -> CaseDetail:
    """Case, latest evaluation, active track and the actions allowed right now."""
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise _not_found(case_id)
        evaluation = _ensure_evaluation(session, case)
        return _detail(session, case, evaluation)


@router.get("/cases/{case_id}/payments", response_model=PaymentListResponse)
def list_case_payments(case_id: str) -> PaymentListResponse:
    """The case's payment history, including voided rows (never deleted)."""
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise _not_found(case_id)
        rows = customer_book.payments_for_case(session, case_id, include_voided=True)
        return PaymentListResponse(
            case_id=case_id,
            payments=[_payment_contract(row) for row in rows],
            count=len(rows),
        )


@router.post("/cases/{case_id}/payments", response_model=CaseDetail)
def create_case_payment(
    case_id: str,
    payload: PaymentCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CaseDetail:
    """Record a payment, re-evaluate through the engine, and audit it.

    The engine already has a payment input (`transaction.part_payments`), so a
    payment is appended there with a `v5:<payment_id>` reference and the case is
    re-evaluated. The v5 `payments` row remains the source of truth; voiding
    removes only the matching engine-input entry and keeps the row.

    A payment cannot be future-dated, cannot precede the invoice, and cannot take
    the total above the engine's remaining claim (invoice amount plus interest
    accrued so far). A financed invoice's receivable belongs to the financier,
    so payments to the supplier are refused with 409.
    """
    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail=(
                "This action needs an Idempotency-Key header so a retry cannot "
                "record the payment twice."
            ),
        )

    body = {"case_id": case_id, **payload.model_dump(mode="json")}
    # Normalise the amount to two places for the idempotency hash, so "100.0"
    # and "100.00" are the same request rather than a false conflict.
    body["amount"] = format(payload.amount.quantize(Decimal("0.01")), "f")
    digest = idempotency.hash_request(body)

    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise _not_found(case_id)

        existing = idempotency.lookup(
            session, key=key, route=ROUTE_CREATE_PAYMENT
        )
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different "
                        "payment request. Use a new key for a new payment."
                    ),
                )
            return CaseDetail.model_validate(existing.response_json)

        financed = _financed_error(session, case.id)
        if financed is not None:
            raise financed

        now = deps.get_adapters().clock.now()
        today = now.date()
        if payload.paid_on > today:
            raise HTTPException(
                status_code=422,
                detail="paid_on cannot be in the future.",
            )
        if payload.paid_on < case.invoice_date:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"paid_on cannot be before the invoice date "
                    f"({case.invoice_date.isoformat()})."
                ),
            )

        current = _ensure_evaluation(session, case)
        remaining, assumption, _ = _remaining_claim(session, case, current)
        if remaining <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "This invoice already appears fully paid; there is no "
                    "outstanding amount to record."
                ),
            )
        if payload.amount > remaining:
            if assumption is None:
                detail = (
                    "This payment would take the total above the invoice amount "
                    f"plus interest accrued so far. The most you can record now is "
                    f"{format(remaining, 'f')}. Check the amount or the payment date."
                )
            else:
                detail = (
                    "This payment would take the total above the invoice amount. "
                    f"The most you can record now is {format(remaining, 'f')}. "
                    "The engine has no interest figure for this case."
                )
            raise HTTPException(status_code=422, detail=detail)

        try:
            payment = customer_book.record_payment(
                session,
                case_id=case.id,
                amount=payload.amount,
                paid_on=payload.paid_on,
                method=payload.method.value,
                note=payload.note,
                actor=EventActor.USER.value,
                at=now,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _add_payment_to_engine_input(session, case, payment)
        evaluation = _reevaluate(session, case)
        _close_recovery_if_paid(
            session,
            case,
            payment,
            evaluation,
            actor=EventActor.USER.value,
        )
        detail = _detail(session, case, evaluation)
        idempotency.store(
            session,
            key=key,
            route=ROUTE_CREATE_PAYMENT,
            request_hash=digest,
            response=detail.model_dump(mode="json"),
        )
        return detail


@router.post(
    "/cases/{case_id}/payments/{payment_id}/void", response_model=CaseDetail
)
def void_case_payment(case_id: str, payment_id: str) -> CaseDetail:
    """Void a payment without deleting it, then re-evaluate through the engine.

    The row keeps its amount and gains `voided_at`; the engine input loses only
    the matching `v5:<payment_id>` entry. Repeating the call is a no-op and
    writes no second event.
    """
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise _not_found(case_id)

        financed = _financed_error(session, case.id)
        if financed is not None:
            raise financed

        payment = session.get(PaymentRow, payment_id)
        if payment is None or payment.case_id != case.id:
            raise HTTPException(
                status_code=404,
                detail=f"No payment with id {payment_id!r} for this case.",
            )

        if payment.voided_at is not None:
            return _detail(session, case, _ensure_evaluation(session, case))

        customer_book.void_payment(
            session,
            payment_id=payment.id,
            actor=EventActor.USER.value,
            at=deps.get_adapters().clock.now(),
        )
        _remove_payment_from_engine_input(session, case, payment.id)
        evaluation = _reevaluate(session, case)
        return _detail(session, case, evaluation)



@router.get("/cases/{case_id}/events", response_model=list[ContractEvent])
def list_case_events(case_id: str) -> list[ContractEvent]:
    """The append-only, hash-chained trail for one case, in sequence order."""
    with session_scope() as session:
        if session.get(CaseRow, case_id) is None:
            raise _not_found(case_id)
        rows = session.exec(
            select(EventRow).where(EventRow.case_id == case_id).order_by(EventRow.seq.asc())
        ).all()
        return [_event_contract(row) for row in rows]


@router.get("/cases/{case_id}/events/verify", response_model=ChainVerifyResult)
def verify_case_events(case_id: str) -> ChainVerifyResult:
    """Recompute the chain and name the first bad sequence, if any.

    Tamper-evident, not tamper-proof: say it that way in the pitch.
    """
    with session_scope() as session:
        if session.get(CaseRow, case_id) is None:
            raise _not_found(case_id)
        result = audit.verify_chain(session, case_id)
    return ChainVerifyResult(
        valid=bool(result["ok"]),
        checked=int(result["checked"]),
        first_bad_seq=result["first_bad_seq"],
    )


# ------------------------------------------------------------ summaries ----


def _invoice_no(request: CaseEvaluationRequest) -> str:
    """The invoice number if the evidence names one, else a labelled stand-in."""
    for item in request.evidence.items:
        if str(item.kind.value).upper() == "INVOICE" and item.ref:
            return str(item.ref)
    return f"{request.case_id}/INV"


def _summary(session, case: CaseRow) -> CaseSummary:
    evaluation = _ensure_evaluation(session, case)
    response = CaseEvaluationResponse.model_validate(evaluation.response_json)
    track = _active_track(session, case.id)
    state = TrackState(track.state) if track is not None else TrackState.NEW

    days_overdue = 0
    if response.timeline is not None and response.timeline.days_overdue is not None:
        days_overdue = int(response.timeline.days_overdue)

    stage = _stage_from_state(state)
    if stage is None and response.evidence_readiness is not None:
        stage = response.evidence_readiness.recommended_stage

    return CaseSummary(
        id=case.id,
        invoice_no=case.invoice_no,
        buyer_gstin=case.buyer_gstin,
        supplier_ref=case.supplier_ref,
        accepted_amount=case.accepted_amount,
        due_date=response.timeline.due_date if response.timeline else None,
        days_overdue=days_overdue,
        calculation_date=evaluation.as_of,
        active_track=_track_contract(track),
        state=state,
        stage=stage,
        available_actions=available_actions(state, track.kind if track else None),
    )
