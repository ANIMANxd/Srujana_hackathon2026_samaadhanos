"""Judge-console clock control (`/api/v1/mock/clock`).

**404 in production, always.** These routes move time, and moving time in a
production system would be a lie about when money was owed. They are refused by
`APP_ENV`, not merely hidden from the UI: a hidden route is still reachable.

In development they drive the `Clock` port. Without `MOCK_CLOCK=1` the adapters hold
a `SystemClock`, which cannot be advanced, so the answer is a clear 400 rather than a
silent no-op — a judge pressing the button twice should learn why nothing moved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app import deps
from backend.adapters.clock import OffsetClock

router = APIRouter(prefix="/api/v1/mock", tags=["mock"])


class ClockAdvance(BaseModel):
    """`advance_days` is forward-only; use `/mock/clock/reset` to wind back."""

    advance_days: int = Field(
        description="Days to move the simulated clock forward. Negative values are refused; reset instead."
    )


def _hidden() -> bool:
    """Whether these routes must pretend not to exist."""
    return deps.is_production()


def _clock():
    """The simulated clock, or a 400 explaining why there isn't one."""
    clock = deps.get_adapters().clock
    if not isinstance(clock, OffsetClock):
        return None
    return clock


def _not_found() -> JSONResponse:
    # Deliberately the same shape as any other missing route: in production the
    # existence of a clock override is itself information.
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": "Not Found", "details": None}},
    )


def _state(clock: OffsetClock) -> dict[str, object]:
    return {
        "now": clock.now().isoformat(),
        "offset_seconds": int(clock.offset.total_seconds()),
        "simulated": True,
    }


@router.post("/clock")
def advance_clock(payload: ClockAdvance):
    """Move the simulated clock. Cases re-evaluate on their next read."""
    if _hidden():
        return _not_found()

    clock = _clock()
    if clock is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "CLOCK_NOT_SIMULATED",
                    "message": (
                        "The clock is real in this process. Start the API with MOCK_CLOCK=1 "
                        "to enable the simulated clock, then try again."
                    ),
                    "details": {"hint": "MOCK_CLOCK=1"},
                }
            },
        )

    try:
        moment = clock.advance(timedelta(days=payload.advance_days))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": {"code": "CLOCK_BACKWARDS", "message": str(exc), "details": None}
            },
        )
    return {"moved_to": moment.isoformat(), **_state(clock)}


@router.post("/clock/reset")
def reset_clock():
    """Put the clock back to real time, so the next demo run starts clean."""
    if _hidden():
        return _not_found()

    clock = _clock()
    if clock is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "CLOCK_NOT_SIMULATED",
                    "message": (
                        "The clock is real in this process. Start the API with MOCK_CLOCK=1 "
                        "to enable the simulated clock, then try again."
                    ),
                    "details": {"hint": "MOCK_CLOCK=1"},
                }
            },
        )

    clock.reset()
    return {"moved_to": clock.now().isoformat(), **_state(clock)}


__all__ = ["router"]
