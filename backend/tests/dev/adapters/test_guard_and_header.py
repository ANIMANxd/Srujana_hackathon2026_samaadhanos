"""The production guard and the `X-Simulation` header.

The guard is the safety rule with teeth: simulated financiers must never be
reachable from a production deployment (golden rule 16). These tests pin the exit
code, the log-free contract (SystemExit), and the header behaviour in both modes.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import deps
from backend.app.main import app


def test_production_with_mock_adapters_exits(monkeypatch, caplog):
    """`APP_ENV=production` + `PROVIDER_MODE=mock` must exit non-zero."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.delenv("MOCK_CLOCK", raising=False)

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as excinfo:
        deps.validate_startup()

    assert excinfo.value.code == 1, "the process must exit non-zero, not 0"
    assert any("REFUSING TO START" in record.message for record in caplog.records)
    assert "mock adapters active" in caplog.text


def test_production_with_a_mock_clock_only_also_exits(monkeypatch, caplog):
    """A simulated clock in production is still a simulation."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.setenv("MOCK_CLOCK", "1")

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as excinfo:
        deps.validate_startup()

    assert excinfo.value.code == 1
    assert "MOCK_CLOCK" in caplog.text


def test_production_with_live_adapters_starts(monkeypatch):
    """live adapters are stubs, but they are not simulations, so startup is allowed."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.delenv("MOCK_CLOCK", raising=False)
    deps.validate_startup()  # must not raise


def test_development_with_mock_adapters_starts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    deps.validate_startup()


def test_an_unknown_provider_mode_exits(monkeypatch, caplog):
    """A typo must not silently fall back to mock."""
    monkeypatch.setenv("PROVIDER_MODE", "sandbox")
    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as excinfo:
        deps.validate_startup()
    assert excinfo.value.code == 1
    assert "PROVIDER_MODE" in caplog.text


def test_the_mock_adapter_set_reports_itself_as_simulated(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    adapters = deps.build_adapters()
    assert adapters.simulated is True
    assert adapters.mode == "mock"


def test_the_live_adapter_set_is_not_simulated(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "live")
    adapters = deps.build_adapters()
    assert adapters.simulated is False
    assert adapters.mode == "live"


# ------------------------------------------------------------- header ----


def test_the_simulation_header_is_present_outside_production(monkeypatch):
    """Every response, not just the ones that look like money."""
    monkeypatch.setenv("APP_ENV", "development")
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Simulation") == "true"


def test_the_simulation_header_is_absent_in_production(monkeypatch):
    """In production the header would be a false label, so it is not sent.

    The client is used without its context manager on purpose: entering it would
    run the startup guard, which is a separate test.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.delenv("MOCK_CLOCK", raising=False)
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert "X-Simulation" not in response.headers


def test_the_header_covers_a_non_health_route(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    client = TestClient(app)
    response = client.get("/api/v1/presets")
    assert response.status_code == 200
    assert response.headers.get("X-Simulation") == "true"
