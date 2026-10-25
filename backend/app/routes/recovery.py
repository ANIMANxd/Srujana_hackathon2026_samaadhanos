"""Recovery track routes: the v3 escalation ladder, now with state.

The artifact templates are **not touched** here. `build_artifact` is the same
function the v1.0 `/generate-artifact` route calls, and its legal content is
whatever the templates already produce; this module only decides *when* a draft may
be prepared and records that the owner prepared or sent it.

Two hard rules from the v4 document:

- **Track locking (section 5.3).** Once the invoice is financed â€” the financing track
  reaching `AWAITING_ESIGN` or later â€” recovery actions are refused with 409, because
  the receivable belongs to the financier. Before that, starting financing *pauses*
  recovery instead of deleting it, and a later recovery start resumes the stage it
  reached.
- **Nothing is sent (golden rule 10).** `mark-sent` records the owner's claim about a
  message they sent from their own phone or mail client. The server has no send path,
  and the audit event says `actor=USER` with the channel they used.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlmodel import select

from backend.app.routes import cases as case_routes
from backend.app.routes import financing as financing_routes
from backend.app.schemas import ArtifactKind, CaseEvaluationRequest, CaseEvaluationResponse, Warning
from backend.app.schemas_v4 import (
    RecoveryActionResponse,
    RecoveryDraft,
    RecoveryMarkSentRequest,
    RecoveryPrepareRequest,
    Track as ContractTrack,
    TrackKind,
    TrackState,
)
from backend.artifacts.generate import build_artifact
from backend.store.db import session_scope
from backend.store.models import Case as CaseRow
from backend.store.models import Track as TrackRow
from backend.workflow import recovery_sm, tracks

router = APIRouter(prefix="/api/v1", tags=["recovery"])

ROUTE_PREPARE = "POST /api/v1/cases/{id}/recovery"
ROUTE_MARK_SENT = "POST /api/v1/cases/{id}/recovery/mark-sent"
ROUTE_ODR_FILED = "POST /api/v1/cases/{id}/recovery/odr-filed"

# The default draft for each stage. Stage 1 has two kinds in the ladder; the balance
# confirmation is the stronger first ask, and `kind` can override it.
STAGE_KINDS: dict[int, ArtifactKind] = {
    1: ArtifactKind.STAGE1_BALANCE_CONFIRMATION,
    2: ArtifactKind.STAGE2_CFO_MEMO,
    3: ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET,
    4: ArtifactKind.STAGE4_EVIDENCE_PACK,
}

LOCKED_MESSAGE = "This invoice is financed; recovery actions are locked."


def _locked() -> JSONResponse:
    return financing_routes._fail(
        409,
        "RECOVERY_LOCKED",
        LOCKED_MESSAGE,
        {"state": TrackState.AWAITING_ESIGN.value, "allowed_events": []},
    )


def _financing_blocks_recovery(session, case_id: str) -> JSONResponse | None:
    """The section 5.3 row that matters most: assigned means locked."""
    active = tracks.active_track(session, case_id)
    if active is None or TrackKind(active.kind) is not TrackKind.FINANCING:
        return None
    decision = tracks.can_start(TrackKind.RECOVERY, active)
    if decision.allowed:
        return None
    return _locked()


def _recovery_track(session, case_id: str) -> TrackRow | None:
    row = session.exec(
        select(TrackRow).where(
            TrackRow.case_id == case_id, TrackRow.kind == TrackKind.RECOVERY.value, TrackRow.closed_at.is_(None)
        )
    ).first()
    return row


def _stage_of(state: str) -> int | None:
    return recovery_sm.stage_number(TrackState(state))


def _detail(session, case: CaseRow, track_row: TrackRow | None):
    return financing_routes._detail(session, case, track_row)


def _response(session, case: CaseRow, track_row: TrackRow | None, **extra) -> RecoveryActionResponse:
    return RecoveryActionResponse(
        detail=_detail(session, case, track_row),
        track=case_routes._track_contract(track_row),
        **extra,
    )


def _draft(
    *, kind: ArtifactKind, stage: int, request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse
) -> RecoveryDraft:
    """Build the draft with the existing generator. No template is modified here."""
    result = build_artifact(kind=kind, request=request, evaluation=evaluation, settlement=None)
    return RecoveryDraft(
        kind=result.kind,
        stage=stage,
        filename=result.filename,
        markdown=result.markdown,
        pdf_filename=result.pdf_filename,
        pdf_base64=result.pdf_base64,
        warnings=[Warning.model_validate(item) for item in result.warnings],
    )


# ------------------------------------------------------------------ routes ----


@router.post("/cases/{case_id}/recovery", response_model=RecoveryActionResponse)
def prepare_recovery(
    case_id: str,
    payload: RecoveryPrepareRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Prepare a stage's draft and move the track to `STAGE_n_PREPARED`.

    Preparing is not sending: the response carries the draft and nothing leaves the
    server.
    """
    key = financing_routes._require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = financing_routes._require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "prepare", "stage": payload.stage}
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise case_routes._not_found(case_id)

        replayed = financing_routes._replay_check(session, key=key, route=ROUTE_PREPARE, body=body)
        if replayed is not None:
            return replayed

        blocked = _financing_blocks_recovery(session, case_id)
        if blocked is not None:
            return blocked

        track_row = _recovery_track(session, case_id)
        if track_row is None:
            if version != 0:
                return financing_routes._fail(
                    409,
                    "STALE_VERSION",
                    "This case has no open recovery track, so If-Match must be 0 to start one.",
                    {"current_state": None, "current_version": 0},
                )
            # Resume the stage a financing attempt paused, rather than starting over.
            resumed = tracks.paused_recovery_state(session, case_id)
            start_state = resumed or TrackState.NEW
            track_row = tracks.open_track(
                session, case_id=case_id, kind=TrackKind.RECOVERY, state=start_state
            )
        elif track_row.version != version:
            return financing_routes._stale(track_row, _detail(session, case, track_row))

        current_stage = _stage_of(track_row.state)
        if current_stage is not None and payload.stage < current_stage:
            return financing_routes._fail(
                409,
                "INVALID_TRANSITION",
                f"The ladder is already at stage {current_stage}; it does not go backwards.",
                {"state": track_row.state, "allowed_events": recovery_sm.allowed_events(TrackState(track_row.state))},
            )

        # Walk the ladder one documented transition at a time: NEW -> STAGE_1_PREPARED
        # -> STAGE_2_PREPARED -> ... and stop at the requested stage.
        for _ in range(4):
            state = TrackState(track_row.state)
            stage_now = _stage_of(state)
            if stage_now is not None and stage_now >= payload.stage:
                break
            try:
                track_row = tracks.apply_transition(
                    session,
                    track_row,
                    event=recovery_sm.RecoveryEvent.PREPARE.value,
                    expected_version=track_row.version,
                    actor="USER",
                    payload={"stage": payload.stage},
                )
            except tracks.InvalidStep as exc:
                return financing_routes._invalid(exc.state, exc.event, exc.allowed, str(exc))

        kind = payload.kind or STAGE_KINDS[payload.stage]
        evaluation_row = case_routes._ensure_evaluation(session, case)
        evaluation = CaseEvaluationResponse.model_validate(evaluation_row.response_json)
        request = CaseEvaluationRequest.model_validate(case.input_json)
        draft = _draft(kind=kind, stage=payload.stage, request=request, evaluation=evaluation)

        response = _response(session, case, track_row, stage=payload.stage, draft=draft)
        financing_routes._record(
            session, key=key, route=ROUTE_PREPARE, body=body, response=response.model_dump(mode="json")
        )
    return response


@router.post("/cases/{case_id}/recovery/mark-sent", response_model=RecoveryActionResponse)
def mark_recovery_sent(
    case_id: str,
    payload: RecoveryMarkSentRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Record that the owner sent this stage from their own client.

    The event stores the channel so the trail is honest about how it went out, and the
    wording stays "the owner says they sent it" â€” the server has no way to know.
    """
    key = financing_routes._require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = financing_routes._require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "mark_sent", "stage": payload.stage, "channel": payload.channel}
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise case_routes._not_found(case_id)
        replayed = financing_routes._replay_check(session, key=key, route=ROUTE_MARK_SENT, body=body)
        if replayed is not None:
            return replayed

        blocked = _financing_blocks_recovery(session, case_id)
        if blocked is not None:
            return blocked

        track_row = _recovery_track(session, case_id)
        if track_row is None:
            return financing_routes._invalid(TrackState.NEW, "mark_sent", ["prepare"])
        if track_row.version != version:
            return financing_routes._stale(track_row, _detail(session, case, track_row))

        expected = f"STAGE_{payload.stage}_PREPARED"
        if track_row.state != expected:
            return financing_routes._fail(
                409,
                "INVALID_TRANSITION",
                f"Stage {payload.stage} is not prepared yet, so there is nothing to mark as sent.",
                {
                    "state": track_row.state,
                    "allowed_events": recovery_sm.allowed_events(TrackState(track_row.state)),
                },
            )

        try:
            track_row = tracks.apply_transition(
                session,
                track_row,
                event=recovery_sm.RecoveryEvent.MARK_SENT.value,
                expected_version=track_row.version,
                actor="USER",
                payload={"stage": payload.stage, "channel": payload.channel, "sent_by": "owner"},
            )
        except tracks.InvalidStep as exc:
            return financing_routes._invalid(exc.state, exc.event, exc.allowed, str(exc))

        response = _response(session, case, track_row, stage=payload.stage, channel=payload.channel)
        financing_routes._record(
            session, key=key, route=ROUTE_MARK_SENT, body=body, response=response.model_dump(mode="json")
        )
    return response


@router.post("/cases/{case_id}/recovery/odr-filed", response_model=RecoveryActionResponse)
def record_odr_filed(
    case_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    """Record that the owner filed on the ODR portal.

    A separate action from `mark-sent` because filing is a different claim: the pack
    being ready is not the same as the owner having submitted it. This is the only
    path to `ODR_FILED_BY_OWNER`.
    """
    key = financing_routes._require_idempotency(idempotency_key)
    if isinstance(key, JSONResponse):
        return key
    version = financing_routes._require_if_match(if_match)
    if isinstance(version, JSONResponse):
        return version

    body = {"case_id": case_id, "action": "odr_filed"}
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise case_routes._not_found(case_id)
        replayed = financing_routes._replay_check(session, key=key, route=ROUTE_ODR_FILED, body=body)
        if replayed is not None:
            return replayed

        track_row = _recovery_track(session, case_id)
        if track_row is None:
            return financing_routes._invalid(TrackState.NEW, "mark_odr_filed", ["prepare"])
        if track_row.version != version:
            return financing_routes._stale(track_row, _detail(session, case, track_row))

        try:
            track_row = tracks.apply_transition(
                session,
                track_row,
                event=recovery_sm.RecoveryEvent.MARK_ODR_FILED.value,
                expected_version=track_row.version,
                actor="USER",
                payload={"filed_by": "owner"},
            )
        except tracks.InvalidStep as exc:
            return financing_routes._invalid(exc.state, exc.event, exc.allowed, str(exc))

        response = _response(session, case, track_row)
        financing_routes._record(
            session, key=key, route=ROUTE_ODR_FILED, body=body, response=response.model_dump(mode="json")
        )
    return response


__all__ = ["router", "LOCKED_MESSAGE", "STAGE_KINDS"]
