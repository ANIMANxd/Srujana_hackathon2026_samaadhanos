"""Dependency wiring and the production guard (architecture_v4 section 6).

One place decides which adapters the app uses, so no route imports a concrete
provider:

    PROVIDER_MODE=mock  -> backend/adapters/mock/  (HTTP to MOCK_PROVIDERS_URL)
    PROVIDER_MODE=live  -> backend/adapters/live/  (stubs, NotImplementedError)

The guard is the important part: a simulated financier must never be reachable from
a production deployment. `validate_startup()` logs a clear error and raises
`SystemExit(1)` so the process exits non-zero rather than serving a demo that looks
like an integration (golden rule 16).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Any

import httpx

from backend.adapters.clock import OffsetClock, SystemClock
from backend.adapters.ids import UlidIdGenerator
from backend.adapters.mock.client import DEFAULT_BASE_URL, MockHttpClient
from backend.adapters.mock import (
    MockDisbursementRail,
    MockESignProvider,
    MockFinancingMarketplace,
)
from backend.adapters.live import (
    LiveDisbursementRail,
    LiveESignProvider,
    LiveFinancingMarketplace,
)
from backend.app.config_loader import CONFIG_PATH
from backend.ports.disbursement import DisbursementRail
from backend.ports.esign import ESignProvider
from backend.ports.marketplace import FinancingMarketplace

log = logging.getLogger(__name__)

PROVIDER_MODES = ("mock", "live")
SIMULATION_HEADER = "X-Simulation"
# A health probe must not slow a page load, so it uses its own short budget rather
# than the 5 s adapter timeout.
HEALTH_PROBE_TIMEOUT = 0.5


@dataclass(frozen=True)
class Adapters:
    """The one container of concrete providers the app is running."""

    esign: ESignProvider
    marketplace: FinancingMarketplace
    disbursement: DisbursementRail
    clock: Any
    ids: Any
    mode: str

    @property
    def simulated(self) -> bool:
        """True when any provider is a simulation."""
        return any(
            getattr(provider, "simulated", False)
            for provider in (self.esign, self.marketplace, self.disbursement)
        )


# ------------------------------------------------------------------ env ----


def app_env() -> str:
    return os.environ.get("APP_ENV", "development").strip().lower()


def is_production() -> bool:
    return app_env() == "production"


def provider_mode() -> str:
    return os.environ.get("PROVIDER_MODE", "mock").strip().lower()


def mock_providers_url() -> str:
    return os.environ.get("MOCK_PROVIDERS_URL", DEFAULT_BASE_URL).strip()


def mock_clock_enabled() -> bool:
    return os.environ.get("MOCK_CLOCK", "").strip().lower() in {"1", "true", "yes", "on"}


def simulation_enabled() -> bool:
    """Whether responses carry `X-Simulation: true` (everything but production)."""
    return not is_production()


def config_version() -> str:
    """A content hash of the statute config actually loaded.

    There is no version field in `statute_config.json`, so the honest "version" is a
    hash of its bytes: it changes exactly when a constant changes, and two demo
    machines showing different money will show different versions.
    """
    try:
        raw = CONFIG_PATH.read_bytes()
    except OSError:  # pragma: no cover - config is shipped
        return "unavailable"
    return hashlib.sha256(raw).hexdigest()[:12]


# --------------------------------------------------------------- wiring ----


def _clock() -> Any:
    base = SystemClock()
    if mock_clock_enabled() and not is_production():
        return OffsetClock(base)
    return base


def build_adapters() -> Adapters:
    """Construct the adapter set for the current environment."""
    mode = provider_mode()
    if mode not in PROVIDER_MODES:
        raise ValueError(
            f"PROVIDER_MODE must be one of {PROVIDER_MODES}, got {mode!r}"
        )

    if mode == "mock":
        client = MockHttpClient(base_url=mock_providers_url())
        return Adapters(
            esign=MockESignProvider(client),
            marketplace=MockFinancingMarketplace(client),
            disbursement=MockDisbursementRail(client),
            clock=_clock(),
            ids=UlidIdGenerator(),
            mode=mode,
        )

    return Adapters(
        esign=LiveESignProvider(),
        marketplace=LiveFinancingMarketplace(),
        disbursement=LiveDisbursementRail(),
        clock=_clock(),
        ids=UlidIdGenerator(),
        mode=mode,
    )


@lru_cache(maxsize=1)
def get_adapters() -> Adapters:
    """Process-wide adapter set. `reset_adapters()` clears it in tests."""
    return build_adapters()


def reset_adapters() -> None:
    get_adapters.cache_clear()


# ---------------------------------------------------------------- guard ----


def validate_startup() -> None:
    """Refuse to serve simulated providers in production.

    Raises `SystemExit(1)` after logging, so uvicorn exits non-zero and a container
    orchestrator sees a failure rather than a healthy-looking demo.
    """
    mode = provider_mode()
    if mode not in PROVIDER_MODES:
        log.critical(
            "REFUSING TO START: PROVIDER_MODE=%r is not one of %s", mode, PROVIDER_MODES
        )
        raise SystemExit(1)

    if not is_production():
        return

    adapters = build_adapters()
    simulated = [
        name
        for name, provider in (
            ("esign", adapters.esign),
            ("marketplace", adapters.marketplace),
            ("disbursement", adapters.disbursement),
        )
        if getattr(provider, "simulated", False)
    ]
    if simulated or mock_clock_enabled():
        reasons = []
        if simulated:
            reasons.append(f"mock adapters active: {', '.join(simulated)}")
        if mock_clock_enabled():
            reasons.append("MOCK_CLOCK is enabled")
        message = (
            "REFUSING TO START: APP_ENV=production but this build is running a simulation "
            f"({'; '.join(reasons)}). Mock providers must never be reachable in production. "
            "Set PROVIDER_MODE=live (and unset MOCK_CLOCK) or unset APP_ENV=production."
        )
        log.critical(message)
        raise SystemExit(1)


# --------------------------------------------------------------- health ----


def probe_mock_providers(transport: httpx.BaseTransport | None = None) -> str:
    """`reachable`, `unreachable` or `not_used`.

    Never raises: health must answer even when the providers are down, and a health
    check that throws is worse than one that reports `unreachable`.
    """
    if provider_mode() != "mock":
        return "not_used"
    try:
        with httpx.Client(timeout=HEALTH_PROBE_TIMEOUT, transport=transport) as client:
            response = client.get(f"{mock_providers_url().rstrip('/')}/health")
        return "reachable" if response.status_code < 500 else "unreachable"
    except httpx.HTTPError:
        return "unreachable"


def database_state() -> str:
    """`ok` when a trivial query answers, `error` otherwise. Never raises."""
    try:
        from sqlmodel import text

        from backend.store.db import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 - health must never throw
        log.warning("store health check failed", exc_info=True)
        return "error"


__all__ = [
    "Adapters",
    "app_env",
    "build_adapters",
    "config_version",
    "database_state",
    "get_adapters",
    "is_production",
    "mock_clock_enabled",
    "mock_providers_url",
    "probe_mock_providers",
    "provider_mode",
    "reset_adapters",
    "simulation_enabled",
    "validate_startup",
]
