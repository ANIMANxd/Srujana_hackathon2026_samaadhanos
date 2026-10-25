"""HTTP client side of the mock provider service (architecture_v4 sections 6 and 7).

Three rules this client exists to enforce:

1. **A hard timeout.** 5 s per call (`DEFAULT_TIMEOUT`), so a wedged mock cannot
   hang a request or the demo.
2. **Retries on connect errors only.** A refused connection is retried; a timeout,
   a 4xx or a 5xx is **not**. Retrying a non-idempotent POST because it timed out
   would risk a double booking, and a timeout is exactly the case where you cannot
   know whether the provider acted.
3. **Correlation forwarding.** The incoming `X-Correlation-Id` is passed through, so
   one demo run is traceable across API → mock → webhook.

Every call also carries `X-Simulation: true`: the mock service is a simulation and
must never be mistaken for an integration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.ports.errors import ProviderUnavailable

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8100"
DEFAULT_TIMEOUT = 5.0

# Connect-error backoff. Two retries, 50 ms then 150 ms: a refused connection on
# localhost is a start-order problem, not a network problem, so the wait is short.
CONNECT_RETRY_DELAYS: tuple[float, ...] = (0.05, 0.15)

SIMULATION_HEADER = "X-Simulation"
CORRELATION_HEADER = "X-Correlation-Id"
IDEMPOTENCY_HEADER = "Idempotency-Key"


@dataclass
class MockHttpClient:
    """Thin synchronous JSON client for the mock provider service."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {SIMULATION_HEADER: "true"}
        if correlation_id:
            headers[CORRELATION_HEADER] = correlation_id
        if idempotency_key:
            headers[IDEMPOTENCY_HEADER] = idempotency_key

        attempts = (0.0, *CONNECT_RETRY_DELAYS)
        last_connect_error: Exception | None = None

        for attempt, delay in enumerate(attempts, start=1):
            if delay:
                import time

                time.sleep(delay)
            try:
                with self._client() as client:
                    response = client.request(method, url, json=json_body, headers=headers)
            except httpx.ConnectError as exc:
                # The only retryable failure: the request never reached the provider.
                last_connect_error = exc
                log.warning("mock provider connect error (%s/%s) %s %s", attempt, len(attempts), method, url)
                continue
            except httpx.TimeoutException as exc:
                # Deliberately not retried: the provider may already have acted.
                raise ProviderUnavailable(f"{method} {url} timed out after {self.timeout}s") from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f"{method} {url} failed: {exc}") from exc

            if response.status_code >= 400:
                raise ProviderUnavailable(
                    f"{method} {url} answered {response.status_code}: {response.text[:200]}"
                )
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:  # pragma: no cover - a mock service bug
                raise ProviderUnavailable(f"{method} {url} returned non-JSON") from exc

        raise ProviderUnavailable(
            f"{method} {url} unreachable after {len(attempts)} attempt(s): {last_connect_error}"
        )
