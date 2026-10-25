"""The five rehearsed judge manipulations, each answered inside one second.

Architecture section 11 lists the five live edits the demo rehearses: change
the delivery date, remove delivery proof, add a mid-period payment, move the
bank-rate epoch (or the enterprise class), and flip the Udyam date past the
Silpi test date. Each test below takes the shipped `case_01` preset, applies
exactly one edit, and checks the status or block the architecture says must
appear - while timing the call (budget: one second).

Grouping: class `TestJudgeManipulations`, marker `judge` - a single
`make test` run labels them (see the report header from
`backend/tests/contract/conftest.py`), and `-m judge` selects only these.

Where the engine's behaviour differs from the document, the test stays failing
and `docs/test-oracles.md` records the finding; nothing is softened here.
"""

import copy
import json
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads(
    (ROOT / "backend" / "presets" / "case_01.json").read_text(encoding="utf-8")
)["request"]

BUDGET_SECONDS = 1.0
MID_PERIOD_PAYMENT = (
    "2026-04-08"  # after the appointed day 2026-04-03, before calc 2026-04-15
)

client = TestClient(app)


def _request(**overrides) -> dict:
    """The preset, deep-copied, with one field edited."""
    request = copy.deepcopy(BASE)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(request.get(key), dict):
            request[key] = {**request[key], **value}
        else:
            request[key] = value
    return request


def _post(request: dict):
    """POST the evaluation and fail if it eats the one-second budget."""
    started = time.perf_counter()
    response = client.post("/api/v1/evaluate-case", json=request)
    elapsed = time.perf_counter() - started
    assert (
        elapsed < BUDGET_SECONDS
    ), f"took {elapsed:.3f}s, over the {BUDGET_SECONDS:.0f}s rehearsal budget"
    assert response.status_code == 200, response.text[:400]
    return response.json()


def _ledger_interest(financials: dict) -> Decimal:
    """Sum of the ledger rows, to compare with the response's own total."""
    return sum(
        (Decimal(row["interest"]) for row in financials["ledger"]), Decimal("0.00")
    )


@pytest.mark.judge
class TestJudgeManipulations:
    """Five rehearsals, one per architecture section 11 live edit."""

    def test_judge_1_change_the_delivery_date(self):
        """Edit: delivery 2026-02-16 -> 2026-02-23 (+7 days).

        Expected (6.2): every downstream date moves by the same seven days -
        window end 2026-03-03 -> 2026-03-10, due 2026-04-02 -> 2026-04-09,
        appointed 2026-04-03 -> 2026-04-10 - and the case still computes.
        """
        baseline = _post(_request())
        shifted = _post(
            _request(
                transaction={"delivery_date": "2026-02-23", "supply_date": "2026-02-23"}
            )
        )

        before, after = baseline["timeline"], shifted["timeline"]
        assert before["due_date"] == "2026-04-02", "the preset's own due date moved"
        assert (
            after["due_date"] == "2026-04-09"
        ), "due must follow the delivery by the same 7 days"
        assert after["appointed_day"] == "2026-04-10"
        assert after["objection_window_end"] == "2026-03-10"
        assert (
            shifted["financials"] is not None
        ), "the case still evaluates after the edit"
        assert shifted["financials"]["ledger"], "with a delay priced there must be rows"

    def test_judge_2_remove_the_delivery_proof(self):
        """Edit: delivery proof removed (no delivery date, evidence withdrawn).

        Expected (6.2, 6.6): objection_status NO_DELIVERY_PROOF, no due date,
        no money block, and Stage 4 blocked - an honest empty state, not zeros.
        """
        edited = _post(
            _request(
                transaction={"delivery_date": None},
                evidence={
                    "items": [
                        (
                            {**item, "present": False, "ref": None}
                            if item["kind"] == "DELIVERY_PROOF"
                            else item
                        )
                        for item in BASE["evidence"]["items"]
                    ]
                },
            )
        )
        timeline = edited["timeline"]
        assert timeline["objection_status"] == "NO_DELIVERY_PROOF"
        assert timeline["due_date"] is None
        assert edited["financials"] is None, "no delivery proof -> no ledger (6.2)"
        assert (
            4 in edited["evidence_readiness"]["blocked_stages"]
        ), "missing delivery proof blocks Stage 4 (6.6)"
        assert any(
            w["severity"] in {"WARN", "BLOCK"} for w in edited["warnings"]
        ), "an absent block must carry a reason in warnings[] (8.1)"

    def test_judge_3_add_a_mid_period_payment(self):
        """Edit: a 100000 payment lands inside the delay (2026-04-08).

        Expected (6.3): the ledger gains the payment, the outstanding principal
        falls below the preset's 1250000.00, and the rows still sum to
        interest_total.
        """
        baseline = _post(_request())
        with_payment = _post(
            _request(
                part_payments=[
                    {
                        "date": MID_PERIOD_PAYMENT,
                        "amount": "100000.00",
                        "reference": "judge-3",
                    }
                ]
            )
        )

        paid_rows = [
            row
            for row in with_payment["financials"]["ledger"]
            if row["payment"] not in ("0.00", "0")
        ]
        assert paid_rows, "the payment must appear in the ledger (6.3)"
        assert (
            paid_rows[0]["from"] <= MID_PERIOD_PAYMENT <= paid_rows[0]["to"]
        ), "the payment row must cover the day the payment was made"
        assert Decimal(with_payment["financials"]["principal_outstanding"]) < Decimal(
            baseline["financials"]["principal_outstanding"]
        ), "a payment must reduce the outstanding principal"
        financials = with_payment["financials"]
        assert _ledger_interest(financials) == Decimal(
            financials["interest_total"]
        ), "rows must still sum to interest_total (section 11)"

    def test_judge_4_move_the_bank_rate_epoch_or_the_enterprise_class(self):
        """Edit A: Bank Rate overridden to 6.00% -> statutory 3 x 6.00 = 18.00%.

        Edit B: investment pushed to 300 crore (past the small ceiling) ->
        EXCLUDED_MEDIUM with no money block, exactly like the shipped case_05a.
        """
        rate_edited = _post(_request(config_overrides={"bank_rate_pct": "6.00"}))
        segments = rate_edited["financials"]["rate_segments"]
        assert segments, "an override still prices the delay"
        for segment in segments:
            assert segment["bank_rate_pct"] == "6.00"
            assert segment["statutory_rate_pct"] == "18.00", "3 x 6.00 = 18.00"

        class_edited = _post(
            _request(supplier={"investment_cr": "300", "turnover_cr": "800"})
        )
        assert class_edited["jurisdiction"]["status"] == "EXCLUDED_MEDIUM"
        assert (
            class_edited["financials"] is None
        ), "an excluded case computes no money (6.1)"
        assert class_edited["jurisdiction"]["alternative_remedy"], "6.1 names a remedy"

    def test_judge_5_flip_the_udyam_date_past_the_silpi_test_date(self):
        """Edit: Udyam registration moved past the Silpi test date (and back).

        Expected (6.1 + section 11, which lists "Silpi blocks"): with the test
        run from the supply date, a registration dated *after* the supply
        (2026-03-01 > 2026-02-16) must fail the chronology check ->
        BARRED_SILPI; the control with the preset's 2023 registration must not
        be barred. If the first assertion fails, docs/test-oracles.md finding F3
        explains why: the check today only confirms the configured date exists.
        """
        override = {"config_overrides": {"silpi_test_date": "SUPPLY"}}
        late = _post(
            _request(supplier={"udyam_registration_date": "2026-03-01"}, **override)
        )
        control = _post(
            _request(supplier={"udyam_registration_date": "2023-06-01"}, **override)
        )

        late_status = late["jurisdiction"]["status"]
        control_status = control["jurisdiction"]["status"]
        late_check = next(
            c for c in late["jurisdiction"]["checks"] if c["id"] == "silpi_chronology"
        )
        assert late_status == "BARRED_SILPI", (
            "registered after the supply date must fail the Silpi chronology check "
            f"(6.1, section 11); got {late_status!r} (check passed={late_check['passed']!r}), "
            f"control with an earlier date got {control_status!r}"
        )
        assert control_status != "BARRED_SILPI", "the control must not be barred"
        assert late_check["passed"] is False
