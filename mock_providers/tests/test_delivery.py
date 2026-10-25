"""Retries, dead letters, and the envelope the API verifies.

Every test injects both the transport and the sleep, so the real 1/2/4/8/16 s backoff
is asserted as *values* without the suite waiting half a minute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from mock_providers import signer
from mock_providers.delivery import BACKOFF_SECONDS, DeliveryService


@dataclass
class FakeResponse:
    status_code: int


class FakeTransport:
    """Records requests and replays a scripted list of status codes."""

    def __init__(self, statuses: list[int], *, raise_on: set[int] | None = None) -> None:
        self.statuses = statuses
        self.raise_on = raise_on or set()
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, *, content, headers, timeout):
        index = len(self.calls)
        self.calls.append(
            {"url": url, "content": content, "headers": dict(headers), "timeout": timeout}
        )
        if index in self.raise_on:
            raise ConnectionError("connection refused")
        status = self.statuses[min(index, len(self.statuses) - 1)]
        return FakeResponse(status)


def _service(transport: FakeTransport, *, dead_letter_path: str | None = None) -> tuple[DeliveryService, list[float]]:
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)

    service = DeliveryService(
        post=transport,
        sleep=sleep,
        backoff=BACKOFF_SECONDS,
        dead_letter_path=dead_letter_path,
    )
    return service, slept


def test_a_first_attempt_success_needs_no_retry(tmp_path):
    transport = FakeTransport([200])
    service, slept = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))

    delivery = service.deliver("esign.completed", {"session_id": "MOCK_ESIGN_1"}, "http://api/hook", "esign")

    assert delivery.delivered is True
    assert delivery.dead_lettered is False
    assert len(delivery.attempts) == 1
    assert slept == [], "a success must not wait"


def test_the_envelope_and_headers_match_the_documented_contract(tmp_path):
    transport = FakeTransport([200])
    service, _ = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))
    service.deliver("esign.completed", {"session_id": "MOCK_ESIGN_1"}, "http://api/hook", "esign")

    call = transport.calls[0]
    body = json.loads(call["content"])
    assert body["event_id"].startswith("MOCK_EVT_")
    assert body["type"] == "esign.completed"
    assert body["created_at"].endswith("Z")
    assert body["data"] == {"session_id": "MOCK_ESIGN_1"}
    assert set(body) == {"event_id", "type", "created_at", "data"}

    headers = call["headers"]
    assert headers["X-Mock-Event-Id"] == body["event_id"]
    assert headers["X-Simulation"] == "true"

    # The signature must verify with the algorithm the API uses.
    assert signer.verify(
        call["content"],
        headers["X-Mock-Timestamp"],
        headers["X-Mock-Signature"],
        signer.secret_for("esign"),
    )


def test_a_non_2xx_is_retried_with_the_documented_backoff(tmp_path):
    transport = FakeTransport([500, 500, 200])
    service, slept = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))

    delivery = service.deliver("bids.available", {"unit_id": "MOCK_UNIT_1"}, "http://api/hook", "marketplace")

    assert delivery.delivered is True
    assert len(delivery.attempts) == 3
    assert slept == [1.0, 2.0], "the first retry waits 1 s, the second 2 s"


def test_the_full_backoff_series_is_used(tmp_path):
    transport = FakeTransport([503])
    service, slept = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))

    service.deliver("payout.processed", {"payout_ref": "MOCK_PAYOUT_1"}, "http://api/hook", "disbursement")

    assert slept == [1.0, 2.0, 4.0, 8.0], "one wait before each retry, five attempts in total"


def test_exhausted_retries_are_dead_lettered(tmp_path):
    dead_letter = tmp_path / "dead_letters.jsonl"
    transport = FakeTransport([500])
    service, slept = _service(transport, dead_letter_path=str(dead_letter))

    delivery = service.deliver("esign.completed", {"session_id": "MOCK_ESIGN_1"}, "http://api/hook", "esign")

    assert delivery.delivered is False
    assert delivery.dead_lettered is True
    assert len(delivery.attempts) == len(BACKOFF_SECONDS) == 5
    assert len(transport.calls) == 5, "five tries on a permanent failure"
    assert slept == [1.0, 2.0, 4.0, 8.0]

    assert service.dead_letters and service.dead_letters[0].event_id == delivery.event_id
    lines = dead_letter.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["dead_lettered"] is True
    assert record["event_id"] == delivery.event_id
    assert len(record["attempts"]) == 5


def test_a_connection_error_is_retried_like_a_failure(tmp_path):
    """A dead API is the most likely failure in a demo, so it must retry too."""
    transport = FakeTransport([200], raise_on={0, 1})
    service, slept = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))

    delivery = service.deliver("fu.accepted", {"unit_id": "MOCK_UNIT_1"}, "http://api/hook", "marketplace")

    assert delivery.delivered is True
    assert len(delivery.attempts) == 3
    assert delivery.attempts[0].status is None
    assert "connection refused" in delivery.attempts[0].error
    assert slept == [1.0, 2.0]


def test_a_duplicate_scenario_sends_the_identical_signed_body(tmp_path):
    """`webhook_duplicate` must reuse the bytes, or the API would see a new event."""
    transport = FakeTransport([200])
    service, _ = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))

    delivery = service.deliver(
        "esign.completed", {"session_id": "MOCK_ESIGN_1"}, "http://api/hook", "esign", duplicate=3
    )

    assert len(transport.calls) == 3
    bodies = {call["content"] for call in transport.calls}
    assert len(bodies) == 1, "one event, delivered three times"
    assert len({call["headers"]["X-Mock-Event-Id"] for call in transport.calls}) == 1
    assert delivery.event_id in bodies.pop().decode()


def test_reset_clears_the_log(tmp_path):
    transport = FakeTransport([200])
    service, _ = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))
    service.deliver("esign.completed", {}, "http://api/hook", "esign")
    assert service.deliveries()

    service.reset()
    assert service.deliveries() == []
    assert service.dead_letters == []


def test_the_delivery_log_is_json_serialisable(tmp_path):
    transport = FakeTransport([200])
    service, _ = _service(transport, dead_letter_path=str(tmp_path / "dl.jsonl"))
    service.deliver("esign.completed", {"a": 1}, "http://api/hook", "esign")
    json.dumps(service.deliveries())
