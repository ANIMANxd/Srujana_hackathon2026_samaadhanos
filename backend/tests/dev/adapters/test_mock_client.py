"""The mock HTTP client: timeout, retry-on-connect-errors-only, header forwarding.

`httpx.MockTransport` lets these tests exercise the real client code (retry loop,
header building, error mapping) without opening a socket.
"""

from __future__ import annotations

import httpx
import pytest

from backend.adapters.mock.client import MockHttpClient
from backend.ports.errors import ProviderUnavailable


def _client(handler) -> tuple[MockHttpClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return MockHttpClient(base_url="http://mock:8100", transport=httpx.MockTransport(record)), seen


def test_a_successful_call_returns_json():
    client, seen = _client(lambda request: httpx.Response(200, json={"session_id": "MOCK-ESIGN-1"}))
    assert client.request("POST", "/esign/sessions", json_body={"a": 1}) == {
        "session_id": "MOCK-ESIGN-1"
    }
    assert len(seen) == 1


def test_a_connect_error_is_retried():
    """A refused connection means the request never arrived, so it is safe to retry."""

    def flaky(request: httpx.Request) -> httpx.Response:
        if len(seen) < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"ok": True})

    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return flaky(request)

    client = MockHttpClient(base_url="http://mock:8100", transport=httpx.MockTransport(record))
    assert client.request("POST", "/x") == {"ok": True}
    assert len(seen) == 3, "one attempt plus the two configured retries"


def test_a_connect_error_that_never_clears_raises_provider_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, seen = _client(refuse)
    with pytest.raises(ProviderUnavailable, match="unreachable"):
        client.request("GET", "/health")
    assert len(seen) == 3, "it must stop after the configured attempts"


def test_a_timeout_is_not_retried():
    """The provider may already have acted, so a retry could double-book."""

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    client, seen = _client(slow)
    with pytest.raises(ProviderUnavailable, match="timed out"):
        client.request("POST", "/marketplace/bids/B1/accept")
    assert len(seen) == 1, "a timeout must never be retried"


def test_a_5xx_is_not_retried():
    client, seen = _client(lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(ProviderUnavailable, match="answered 500"):
        client.request("POST", "/esign/sessions")
    assert len(seen) == 1


def test_a_4xx_is_not_retried():
    client, seen = _client(lambda request: httpx.Response(400, text="bad"))
    with pytest.raises(ProviderUnavailable):
        client.request("POST", "/esign/sessions")
    assert len(seen) == 1


def test_the_simulation_and_correlation_headers_are_forwarded():
    client, seen = _client(lambda request: httpx.Response(200, json={}))
    client.request(
        "POST",
        "/marketplace/factoring-units",
        json_body={"invoice_no": "INV-0042"},
        correlation_id="corr-123",
        idempotency_key="idem-456",
    )
    headers = seen[0].headers
    assert headers["X-Simulation"] == "true", "every mock call is labelled"
    assert headers["X-Correlation-Id"] == "corr-123"
    assert headers["Idempotency-Key"] == "idem-456"


def test_the_timeout_is_five_seconds_by_default():
    """A wedged mock must not hang a request."""
    assert MockHttpClient().timeout == 5.0


def test_an_empty_body_returns_an_empty_dict():
    """`open_bidding` has no meaningful response body."""
    client, _ = _client(lambda request: httpx.Response(204))
    assert client.request("POST", "/marketplace/factoring-units/U1/bidding") == {}
