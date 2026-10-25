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
    TrackState,
)
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case as evaluate_case_engine
from backend.store import audit
from backend.store.db import session_scope
from backend.store.ids import new_ulid
from backend.store.models import Case as CaseRow
from backend.store.models import Evaluation as EvaluationRow
from backend.store.models import Event as EventRow
from backend.store.models import Track as TrackRow
from backend.workflow.transitions import available_actions

router = APIRouter(prefix="/api/v1", tags=["cases"])


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
