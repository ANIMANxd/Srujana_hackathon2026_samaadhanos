"""The mock provider service: a separate FastAPI app on :8100.

**SIMULATION ONLY.** Three providers â€” eSign, a TReDS-style marketplace and a bank â€”
behave like real asynchronous providers: they answer immediately with a pending
status, then POST a **signed** webhook back to the API after a delay. That is what
exercises the API's signature check, inbox dedupe, parking and retry paths with real
traffic.

This process imports nothing from `backend/`. It must be startable on its own, and
it must be impossible for a simulation to reach into a legal rule or a database.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mock_providers import bank, esign, marketplace, scenarios
from mock_providers.delivery import service
from mock_providers.state import store

log = logging.getLogger(__name__)

BANNER = "SIMULATION ONLY. Fictional names. No real money, no real signatures, no Aadhaar data."


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Refuse to start in production: a simulation must never be reachable there."""
    if os.environ.get("APP_ENV", "development").strip().lower() == "production":
        log.critical(
            "REFUSING TO START: mock_providers is a simulation service and must never "
            "run with APP_ENV=production."
        )
        raise SystemExit(1)
    yield


app = FastAPI(
    title="SamadhaanOS mock providers",
    version="0.1.0",
    lifespan=_lifespan,
    description=BANNER,
)



@app.middleware("http")
async def _simulation_header(request: Request, call_next):
    """Label every response, so no screenshot can pass this off as an integration."""
    response = await call_next(request)
    response.headers["X-Simulation"] = "true"
    return response


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "mock_providers",
        "simulation": "true",
        "scenarios": dict(store.scenarios),
    }


@app.post("/mock/reset")
def reset() -> dict:
    """Clear every in-memory object and the delivery log."""
    store.reset()
    service.reset()
    return {"reset": True, "simulation": "true"}


@app.get("/mock/deliveries")
def deliveries(limit: int = 50) -> dict:
    """The last `limit` deliveries with their status, for the judge console.

    Newest first. Each row carries the event id, type, provider, how many attempts it
    took, and whether it was delivered or dead-lettered, so a judge can point at a
    retry rather than describe one.
    """
    invent = list(reversed(service.deliveries()))[: max(1, min(limit, 200))]
    return {
        "count": len(invent),
        "deliveries": [
            {
                **item,
                "status": "DELIVERED" if item["delivered"] else ("DEAD_LETTER" if item["dead_lettered"] else "PENDING"),
                "attempt_count": len(item["attempts"]),
            }
            for item in invent
        ],
        "dead_letters": [item.as_dict() for item in service.dead_letters][-limit:],
    }


@app.get("/mock/banner")
def banner() -> JSONResponse:
    return JSONResponse({"banner": BANNER})


app.include_router(esign.router)
app.include_router(marketplace.router)
app.include_router(bank.router)
app.include_router(scenarios.router)
