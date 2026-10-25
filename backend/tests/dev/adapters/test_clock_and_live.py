"""Clocks, id generation, and the live stubs that refuse to pretend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.adapters.clock import OffsetClock, SystemClock
from backend.adapters.ids import SeededIdGenerator, UlidIdGenerator
from backend.adapters.live import (
    LiveDisbursementRail,
    LiveESignProvider,
    LiveFinancingMarketplace,
)
from backend.app import deps
from backend.ports.esign import SignableDoc, SignerRef
from backend.ports.marketplace import FactoringUnitIn, FactoringUnitRef


def test_the_system_clock_is_timezone_aware():
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_the_offset_clock_advances_without_a_real_wait():
    """The judge console's "jump to day 46" must be instant and deterministic."""
    clock = OffsetClock(SystemClock())
    before = clock.now()
    later = clock.advance(timedelta(days=45))
    assert later == clock.now()
    assert later > before
    assert clock.offset == timedelta(days=45)


def test_the_offset_clock_refuses_to_move_backwards():
    clock = OffsetClock(SystemClock())
    with pytest.raises(ValueError, match="only move forward"):
        clock.advance(timedelta(days=-1))


def test_the_offset_clock_is_installed_only_when_asked(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MOCK_CLOCK", raising=False)
    assert deps.build_adapters().clock.simulated is False

    monkeypatch.setenv("MOCK_CLOCK", "1")
    clock = deps.build_adapters().clock
    assert isinstance(clock, OffsetClock)
    assert clock.simulated is True


def test_the_mock_clock_is_ignored_in_production(monkeypatch):
    """Even though the guard exits in production, the clock must not move either."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.setenv("MOCK_CLOCK", "1")
    assert isinstance(deps.build_adapters().clock, SystemClock)


# ------------------------------------------------------------------ ids ----


def test_ulids_are_prefixed_and_unique():
    generator = UlidIdGenerator()
    first, second = generator.new_id("CASE"), generator.new_id("CASE")
    assert first.startswith("CASE-")
    assert first != second


def test_the_seeded_generator_is_deterministic():
    generator = SeededIdGenerator()
    assert generator.new_id("TRK") == "TRK-0001"
    assert generator.new_id("TRK") == "TRK-0002"
    assert generator.new_id("BID") == "BID-0001", "counters are per prefix"


# ---------------------------------------------------------------- live ----


DOC = SignableDoc(doc_id="DOC-1", doc_sha256="a" * 64, title="Financing request (DEMO TEMPLATE)")
SIGNER = SignerRef(display_name="Demo Signer")
UNIT = FactoringUnitIn(invoice_no="INV-0042", buyer_gstin=None, amount=__import__("decimal").Decimal("1250000.00"), due_date=datetime(2026, 10, 29, tzinfo=UTC).date())
REF = FactoringUnitRef(unit_id="MOCK-UNIT-1")


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.create_session(DOC, SIGNER, "idem-1"),
        lambda p: p.get_session("MOCK-ESIGN-1"),
    ],
)
def test_the_live_esign_provider_is_not_integrated(call):
    with pytest.raises(NotImplementedError, match="live provider not integrated"):
        call(LiveESignProvider())


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.register_invoice(UNIT, "idem-1"),
        lambda p: p.request_buyer_acceptance(REF),
        lambda p: p.get_acceptance(REF),
        lambda p: p.open_bidding(REF, timedelta(hours=24)),
        lambda p: p.list_bids(REF),
        lambda p: p.accept_bid(REF, "MOCK-BID-1", "idem-1"),
    ],
)
def test_the_live_marketplace_is_not_integrated(call):
    with pytest.raises(NotImplementedError, match="live provider not integrated"):
        call(LiveFinancingMarketplace())


def test_the_live_disbursement_rail_is_not_integrated():
    with pytest.raises(NotImplementedError, match="live provider not integrated"):
        LiveDisbursementRail().get_payout("MOCK-PAYOUT-1")


def test_live_adapters_never_claim_to_be_simulated():
    assert LiveESignProvider().simulated is False
    assert LiveFinancingMarketplace().simulated is False
    assert LiveDisbursementRail().simulated is False
