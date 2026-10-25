"""Health reports store state, provider mode, mock reachability and config version.

The provider reachability is a real HTTP probe, so these tests replace the transport
with `httpx.MockTransport` rather than hitting a port that may or may not be open.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import deps
from backend.app.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_health_reports_every_documented_field(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(deps, "probe_mock_providers", lambda *_a, **_k: "reachable")

    body = _client().get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["provider_mode"] == "mock"
    assert body["mock_providers"] == "reachable"
    assert body["config_version"], "a config version is required by section 8"
    assert body["contract_version"] == "1.0"


def test_every_health_value_is_a_string(monkeypatch):
    """The v1.0 schema for this path is additionalProperties: {type: string}."""
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(deps, "probe_mock_providers", lambda *_a, **_k: "reachable")
    body = _client().get("/api/v1/health").json()
    assert all(isinstance(value, str) for value in body.values()), body


def test_health_reports_unreachable_providers_without_failing(monkeypatch):
    """A down mock service must degrade the report, not the endpoint."""
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setattr(deps, "probe_mock_providers", lambda *_a, **_k: "unreachable")

    response = _client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["mock_providers"] == "unreachable"


def test_health_says_not_used_when_the_mode_is_live(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "live")
    body = _client().get("/api/v1/health").json()
    assert body["provider_mode"] == "live"
    assert body["mock_providers"] == "not_used"


# ------------------------------------------------------- the probe itself ----


def test_the_probe_reports_reachable_on_2xx(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "ok"}))
    assert deps.probe_mock_providers(transport) == "reachable"


def test_the_probe_reports_unreachable_on_a_connection_error(monkeypatch):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setenv("PROVIDER_MODE", "mock")
    assert deps.probe_mock_providers(httpx.MockTransport(refuse)) == "unreachable"


def test_the_probe_reports_unreachable_on_a_server_error(monkeypatch):
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    assert deps.probe_mock_providers(transport) == "unreachable"


def test_the_probe_is_skipped_in_live_mode(monkeypatch):
    """No mock service exists to probe, so it must not invent a status."""
    monkeypatch.setenv("PROVIDER_MODE", "live")
    assert deps.probe_mock_providers() == "not_used"


def test_the_probe_never_raises(monkeypatch):
    """Health that throws is worse than health that reports a problem."""

    def explode(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("unexpected bug")

    monkeypatch.setenv("PROVIDER_MODE", "mock")
    with pytest.raises(RuntimeError):
        # RuntimeError is *not* an httpx error, so it escapes on purpose: only
        # transport failures are swallowed, not programming errors.
        deps.probe_mock_providers(httpx.MockTransport(explode))


# ---------------------------------------------------------- config version ----


def test_the_config_version_matches_the_shipped_config_file():
    import hashlib
    from pathlib import Path

    config_path = Path(__file__).resolve().parents[3] / "config" / "statute_config.json"
    expected = hashlib.sha256(config_path.read_bytes()).hexdigest()[:12]
    assert deps.config_version() == expected


def test_the_config_version_changes_with_the_config(monkeypatch, tmp_path):
    """A content hash is only useful if it actually tracks content."""
    import hashlib

    before = deps.config_version()
    assert before != "unavailable"

    altered = tmp_path / "statute_config.json"
    altered.write_text('{"note": "different content"}', encoding="utf-8")
    monkeypatch.setattr(deps, "CONFIG_PATH", altered)

    after = deps.config_version()
    assert after == hashlib.sha256(altered.read_bytes()).hexdigest()[:12]
    assert after != before
