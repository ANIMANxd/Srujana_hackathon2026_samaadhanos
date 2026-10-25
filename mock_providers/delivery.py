"""Signed webhook delivery with retries and a dead-letter log.

The mock behaves like a real asynchronous provider: it returns immediately (the
route schedules this as a background task), then POSTs a **signed** event to the
API. That is what gives the API's verification, deduplication and parking code real
traffic to handle instead of a simulation of traffic.

Retry policy (`docs/webhooks.md`): non-2xx is retried with backoff 1, 2, 4, 8, 16
seconds, then the event is dead-lettered. Every attempt is recorded, so the demo can
show exactly what happened rather than a spinner.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from mock_providers import signer

# Section 8 of the v4 document. Not a legal constant: a delivery schedule.
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)

ATTEMPT_TIMEOUT = 5.0


@dataclass
class Attempt:
    """One HTTP attempt, kept so the judge console can show the retries."""

    at: str
    status: int | None
    error: str | None = None


@dataclass
class Delivery:
    """One event and everything that happened to it."""

    event_id: str
    type: str
    provider: str
    target_url: str
    created_at: str
    payload: dict[str, Any]
    attempts: list[Attempt] = field(default_factory=list)
    delivered: bool = False
    dead_lettered: bool = False
    body: bytes = b""

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "provider": self.provider,
            "target_url": self.target_url,
            "created_at": self.created_at,
            "delivered": self.delivered,
            "dead_lettered": self.dead_lettered,
            "attempts": [
                {"at": attempt.at, "status": attempt.status, "error": attempt.error}
                for attempt in self.attempts
            ],
        }


class DeliveryService:
    """Signs, posts, retries, and remembers. One instance per process."""

    def __init__(
        self,
        *,
        post: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None,
        backoff: tuple[float, ...] = BACKOFF_SECONDS,
        dead_letter_path: str | None = "mock_providers/dead_letter.jsonl",
    ) -> None:
        self._post = post or self._http_post
        self._sleep = sleep or time.sleep
        self._backoff = backoff
        self._dead_letter_path = dead_letter_path
        self.log: list[Delivery] = []
        self.dead_letters: list[Delivery] = []

    # -- transport ---------------------------------------------------------

    @staticmethod
    def _http_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        return httpx.post(url, content=content, headers=headers, timeout=timeout)

    # -- public ------------------------------------------------------------

    def build(self, event_type: str, payload: dict[str, Any], target_url: str, provider: str) -> Delivery:
        """The envelope `{event_id, type, created_at, data}` plus its signed bytes."""
        created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        envelope = {
            "event_id": signer.new_id("EVT"),
            "type": event_type,
            "created_at": created,
            "data": payload,
        }
        body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        return Delivery(
            event_id=envelope["event_id"],
            type=event_type,
            provider=provider,
            target_url=target_url,
            created_at=created,
            payload=payload,
            body=body,
        )

    def deliver(
        self,
        event_type: str,
        payload: dict[str, Any],
        target_url: str,
        provider: str,
        *,
        duplicate: int = 1,
    ) -> Delivery:
        """Deliver one event, retrying non-2xx. Returns the delivery record.

        `duplicate=N` sends the exact same signed body N times, which is how the
        `webhook_duplicate` scenario proves the API's dedupe does nothing twice.
        """
        delivery = self.build(event_type, payload, target_url, provider)
        secret = signer.secret_for(provider)

        for _ in range(max(1, duplicate)):
            self._attempt_until_done(delivery, secret)

        self.log.append(delivery)
        if delivery.dead_lettered:
            self.dead_letters.append(delivery)
            self._write_dead_letter(delivery)
        return delivery

    # -- internals ---------------------------------------------------------

    def _attempt_until_done(self, delivery: Delivery, secret: str) -> None:
        for index in range(len(self._backoff)):
            if index:
                # Wait the documented backoff *before* retry `index`.
                self._sleep(self._backoff[index - 1])
            timestamp = str(int(time.time()))
            headers = {
                "Content-Type": "application/json",
                "X-Mock-Event-Id": delivery.event_id,
                "X-Mock-Timestamp": timestamp,
                "X-Mock-Signature": signer.sign(delivery.body, timestamp, secret),
                "X-Simulation": "true",
            }
            try:
                response = self._post(
                    delivery.target_url,
                    content=delivery.body,
                    headers=headers,
                    timeout=ATTEMPT_TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001 - a dead API is a retryable failure
                delivery.attempts.append(
                    Attempt(at=_now(), status=None, error=f"{type(exc).__name__}: {exc}")
                )
                continue

            status = int(getattr(response, "status_code", 0))
            delivery.attempts.append(Attempt(at=_now(), status=status))
            if 200 <= status < 300:
                delivery.delivered = True
                return

        delivery.dead_lettered = True

    def _write_dead_letter(self, delivery: Delivery) -> None:
        if not self._dead_letter_path:
            return
        try:
            with open(self._dead_letter_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(delivery.as_dict(), separators=(",", ":")) + "\n")
        except OSError:
            # A read-only filesystem must not break a delivery attempt.
            pass

    # -- introspection -----------------------------------------------------

    def reset(self) -> None:
        self.log.clear()
        self.dead_letters.clear()

    def deliveries(self) -> list[dict[str, Any]]:
        return [delivery.as_dict() for delivery in self.log]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# The process-wide service. `app.py` schedules `deliver` as a background task.
service = DeliveryService()
