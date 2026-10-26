"""Customer-book routes (contract v1.2): read model, sorting, groups and undo.

The tests deliberately do not recompute a legal figure. They check wiring:

- the list sorts on the `backend/insights/` figures and never shows an average
  below `insights.min_history` (AGENTS.md rule 25);
- a group row's totals equal the sum of its members, and its averages stay null;
- attach/detach is an exact round trip with an audit event on every affected case;
- a dismissed suggestion stays dismissed;
- days-to-pay are measured from the engine's day of acceptance, not the invoice
  date, and "on time" means paid by the engine's due date;
- the insights payload has the shape and the wording the rules require.
"""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from backend.app import deps
from backend.store import db as store_db
from backend.store.models import Case, Customer, Event

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

PAN_GSTIN_A = "29ABCDE1234F1Z5"  # PAN ABCDE1234F
PAN_GSTIN_B = "27PQRSX5678K1Z3"  # PAN PQRSX5678K, a different legal entity
INVALID_GSTIN = "29SYN000000009Z1"
INVALID_GSTIN_B = "29SYN000000003Z1"


# ----------------------------------------------------------------- helpers ----


def _today() -> date:
    return deps.get_adapters().clock.now().date()


def _request(
    *,
    gstin: str | None,
    name: str,
    principal: str = "100000.00",
    days_since_delivery: int = 60,
    invoice_no: str = "INV-CB-1",
) -> dict:
    """A preset-shaped request with the buyer and the dates moved.

    Delivery is `days_since_delivery` before the demo day, so the engine's
    acceptance date is that day (there is no objection), the invoice date is five
    days earlier still, and the s.15 cap gives a due date at acceptance + 45.
    """
    payload = copy.deepcopy(PRESET)
    payload["buyer"] = {
        **payload["buyer"],
        "gstin": gstin,
        "name": name,
    }
    today = _today()
    delivery = today - timedelta(days=days_since_delivery)
    transaction = payload["transaction"]
    transaction["delivery_date"] = delivery.isoformat()
    transaction["supply_date"] = delivery.isoformat()
    transaction["invoice_date"] = (delivery - timedelta(days=5)).isoformat()
    transaction["contract_date"] = (delivery - timedelta(days=30)).isoformat()
    transaction["calculation_date"] = today.isoformat()
    transaction["principal"] = principal
    payload["objections"] = []
    payload["part_payments"] = []
    payload["acknowledgments"] = []
    payload["evidence"]["items"] = [
        {**item, "ref": f"{invoice_no}-{item['kind']}"}
        for item in payload["evidence"]["items"]
    ]
    return payload


def _create(client: TestClient, **kwargs) -> str:
    response = client.post("/api/v1/cases", json=_request(**kwargs))
    assert response.status_code == 201, response.text[:600]
    return response.json()["case"]["id"]


def _customer_id(case_id: str) -> str:
    with store_db.session_scope() as session:
        row = session.get(Case, case_id)
        assert row is not None
        assert row.customer_id, "the case was not attached to a customer"
        return row.customer_id


def _customer_row(case_id: str):
    with store_db.session_scope() as session:
        row = session.get(Case, case_id)
        assert row is not None and row.customer_id
        return session.get(Customer, row.customer_id)


def _customer_exists(customer_id: str) -> bool:
    with store_db.session_scope() as session:
        return session.get(Customer, customer_id) is not None


def _entries(client: TestClient, **params) -> list[dict]:
    response = client.get("/api/v1/customers", params=params)
    assert response.status_code == 200, response.text[:600]
    return response.json()["entries"]


def _find(entries: list[dict], customer_id: str) -> dict:
    for entry in entries:
        if entry["customer"] and entry["customer"]["id"] == customer_id:
            return entry
    raise AssertionError(f"customer {customer_id} not in the list")


def _profile(client: TestClient, customer_id: str) -> dict:
    response = client.get(f"/api/v1/customers/{customer_id}")
    assert response.status_code == 200, response.text[:600]
    return response.json()


def _events(case_id: str) -> list[Event]:
    with store_db.session_scope() as session:
        return list(
            session.exec(
                select(Event).where(Event.case_id == case_id).order_by(Event.seq)
            ).all()
        )


def _pay(client: TestClient, case_id: str, amount: str, key: str) -> None:
    response = client.post(
        f"/api/v1/cases/{case_id}/payments",
        json={
            "amount": amount,
            "paid_on": _today().isoformat(),
            "method": "bank",
            "note": "synthetic",
        },
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text[:600]


# ------------------------------------------------------------ the list ----


def test_the_list_sorts_on_the_engine_figures_and_shows_the_sample_size(client):
    beta = _create(client, gstin=INVALID_GSTIN, name="Beta Traders Pvt Ltd", principal="500000.00")
    alpha = _create(client, gstin=INVALID_GSTIN_B, name="Alpha Corp", principal="100000.00")
    gamma_case = _create(
        client, gstin=None, name="Gamma Ltd", principal="300000.00"
    )

    by_outstanding = _entries(client, sort="outstanding")
    amounts = [Decimal(entry["customer"]["stats"]["outstanding_total"]) for entry in by_outstanding]
    assert amounts == sorted(amounts, reverse=True), "outstanding must sort largest first"
    assert by_outstanding[0]["customer"]["id"] == _customer_id(beta)
    assert by_outstanding[-1]["customer"]["id"] == _customer_id(alpha)

    by_name = _entries(client, sort="name")
    names = [entry["display_name"].casefold() for entry in by_name]
    assert names == sorted(names), "name must sort A-Z"

    # Every row carries the descriptive summary and says when it has no history.
    for entry in by_outstanding:
        stats = entry["customer"]["stats"]
        assert Decimal(stats["outstanding_total"]) >= 0
        assert Decimal(stats["overdue_total"]) >= 0
        assert isinstance(stats["interest_accrued_now"], str)
        assert stats["based_on"] < stats["min_history"]
        assert stats["avg_days_to_pay"] is None
        assert "Not enough history" in stats["avg_days_to_pay_reason"]

    # A money sort never invents a figure to rank a customer without history.
    by_avg = _entries(client, sort="avg_days")
    assert all(entry["customer"]["stats"]["avg_days_to_pay"] is None for entry in by_avg)
    assert [entry["display_name"].casefold() for entry in by_avg] == sorted(
        entry["display_name"].casefold() for entry in by_avg
    )

    # A GSTIN-less buyer is its own provisional customer, never merged by name.
    assert len({_customer_id(gamma_case), _customer_id(alpha), _customer_id(beta)}) == 3


def test_sorting_by_overdue_uses_the_engine_due_dates(client):
    overdue = _create(
        client,
        gstin=INVALID_GSTIN,
        name="Overdue Buyer Ltd",
        principal="400000.00",
        days_since_delivery=90,
    )
    not_due = _create(
        client,
        gstin=INVALID_GSTIN_B,
        name="Not Due Buyer Ltd",
        principal="900000.00",
        days_since_delivery=5,
    )

    entries = _entries(client, sort="overdue")
    assert entries[0]["customer"]["id"] == _customer_id(overdue)
    assert Decimal(entries[0]["customer"]["stats"]["overdue_total"]) > 0
    last = _find(entries, _customer_id(not_due))
    assert Decimal(last["customer"]["stats"]["overdue_total"]) == Decimal("0.00")
    assert entries[-1]["customer"]["id"] == _customer_id(not_due)


# --------------------------------------------------------------- groups ----


def test_a_group_row_totals_equal_the_sum_of_its_members(client):
    first = _create(
        client,
        gstin=PAN_GSTIN_A,
        name="Acme Industries Private Limited",
        principal="600000.00",
    )
    second = _create(
        client,
        gstin=PAN_GSTIN_B,
        name="Acme Industries Pvt Ltd",
        principal="250000.00",
        days_since_delivery=20,
    )
    first_id, second_id = _customer_id(first), _customer_id(second)
    assert first_id != second_id, "different PANs are never merged automatically"

    created = client.post(
        "/api/v1/customer-groups",
        json={"label": "Acme group (synthetic)", "customer_ids": [first_id, second_id]},
        headers={"Idempotency-Key": "group-create-1"},
    )
    assert created.status_code == 201, created.text[:600]
    group = created.json()
    assert group["member_count"] == 2

    entries = _entries(client, group="true")
    groups = [entry for entry in entries if entry["kind"] == "GROUP"]
    assert len(groups) == 1
    entry = groups[0]
    members = entry["group"]["members"]
    assert {member["id"] for member in members} == {first_id, second_id}

    # The group replaces its members in the list.
    listed_customers = {e["customer"]["id"] for e in entries if e["kind"] == "CUSTOMER"}
    assert first_id not in listed_customers and second_id not in listed_customers

    totals = entry["group"]["stats"]
    for field in ("outstanding_total", "overdue_total", "paid_total", "interest_accrued_now"):
        expected = sum((Decimal(member["stats"][field]) for member in members), Decimal("0.00"))
        assert Decimal(totals[field]) == expected, f"group {field} is not the sum of its members"
    assert totals["invoice_count"] == sum(member["stats"]["invoice_count"] for member in members)
    assert totals["paid_count"] == sum(member["stats"]["paid_count"] for member in members)

    # Counts add up; averages would not, so they stay null with a reason.
    assert totals["avg_days_to_pay"] is None
    assert "averages do not" in totals["avg_days_to_pay_reason"]
    assert entry["group"]["totals_note"] == totals["avg_days_to_pay_reason"]

    # Without `group=true` both customers are listed individually.
    plain = {e["customer"]["id"] for e in _entries(client) if e["kind"] == "CUSTOMER"}
    assert {first_id, second_id} <= plain


def test_group_membership_is_idempotent_audited_and_removable(client):
    first = _customer_id(
        _create(client, gstin=PAN_GSTIN_A, name="Acme Industries Private Limited")
    )
    second = _customer_id(
        _create(client, gstin=PAN_GSTIN_B, name="Acme Industries Pvt Ltd")
    )
    third_case = _create(client, gstin=INVALID_GSTIN, name="Delta Component Works")
    third = _customer_id(third_case)

    created = client.post(
        "/api/v1/customer-groups",
        json={"label": "Acme group (synthetic)", "customer_ids": [first, second]},
        headers={"Idempotency-Key": "group-create-2"},
    )
    assert created.status_code == 201, created.text[:600]
    group_id = created.json()["id"]

    added = client.post(
        f"/api/v1/customer-groups/{group_id}/members",
        json={"customer_id": third},
        headers={"Idempotency-Key": "group-add-1"},
    )
    assert added.status_code == 200, added.text[:600]
    assert added.json()["changed"] is True
    assert added.json()["group"]["member_count"] == 3
    assert "customer.group_linked" in [event.type for event in _events(third_case)]

    again = client.post(
        f"/api/v1/customer-groups/{group_id}/members",
        json={"customer_id": third},
        headers={"Idempotency-Key": "group-add-2"},
    )
    assert again.status_code == 200, again.text[:600]
    assert again.json()["changed"] is False, "adding the same member twice changes nothing"

    removed = client.request(
        "DELETE",
        f"/api/v1/customer-groups/{group_id}/members/{third}",
        headers={"Idempotency-Key": "group-remove-1"},
    )
    assert removed.status_code == 200, removed.text[:600]
    assert removed.json()["changed"] is True
    assert removed.json()["group"]["member_count"] == 2
    assert "customer.group_unlinked" in [event.type for event in _events(third_case)]

    removed_again = client.request(
        "DELETE",
        f"/api/v1/customer-groups/{group_id}/members/{third}",
        headers={"Idempotency-Key": "group-remove-2"},
    )
    assert removed_again.status_code == 200
    assert removed_again.json()["changed"] is False


def test_a_customer_can_only_be_in_one_group(client):
    first = _customer_id(_create(client, gstin=PAN_GSTIN_A, name="Acme Industries Private Limited"))
    second = _customer_id(_create(client, gstin=PAN_GSTIN_B, name="Acme Industries Pvt Ltd"))

    created = client.post(
        "/api/v1/customer-groups",
        json={"label": "Acme group (synthetic)", "customer_ids": [first]},
        headers={"Idempotency-Key": "group-create-3"},
    )
    assert created.status_code == 201, created.text[:600]

    clash = client.post(
        "/api/v1/customer-groups",
        json={"label": "Second group (synthetic)", "customer_ids": [first, second]},
        headers={"Idempotency-Key": "group-create-4"},
    )
    assert clash.status_code == 409, clash.text[:600]
    assert "already in another group" in clash.json()["error"]["message"]


# ------------------------------------------------------ attach and detach ----


def test_attach_and_detach_is_a_reversible_audited_roundtrip(client):
    provisional_case = _create(
        client,
        gstin=INVALID_GSTIN,
        name="Roundtrip Buyer Pvt Ltd",
        principal="300000.00",
    )
    pan_case = _create(
        client,
        gstin=PAN_GSTIN_A,
        name="Roundtrip Buyer Private Limited",
        principal="200000.00",
    )
    provisional_id = _customer_id(provisional_case)
    pan_id = _customer_id(pan_case)
    assert provisional_id != pan_id

    attached = client.post(
        f"/api/v1/customers/{provisional_id}/attach",
        json={"target_customer_id": pan_id},
        headers={"Idempotency-Key": "attach-roundtrip-1"},
    )
    assert attached.status_code == 200, attached.text[:800]
    body = attached.json()
    assert body["case_ids"] == [provisional_case]
    assert INVALID_GSTIN in body["gstins"]
    assert provisional_case in body["audited_case_ids"]
    assert _customer_id(provisional_case) == pan_id, "the invoice moved to the target"

    # The provisional record stays (with no invoices) so this can be undone.
    assert _customer_exists(provisional_id), "the undo anchor must survive the attach"
    listed = {entry["id"] for entry in _entries(client)}
    assert provisional_id not in listed, "a customer with no invoices is not a row"

    profile = _profile(client, pan_id)
    assert {invoice["case_id"] for invoice in profile["invoices"]} == {
        provisional_case,
        pan_case,
    }
    assert any(event["type"] == "customer.attach" for event in profile["timeline"])
    assert any(item["payload_json"].get("from_customer_id") == provisional_id for item in profile["timeline"])

    # A replay with the same key returns the stored response and writes nothing.
    events_before = len(_events(provisional_case))
    replay = client.post(
        f"/api/v1/customers/{provisional_id}/attach",
        json={"target_customer_id": pan_id},
        headers={"Idempotency-Key": "attach-roundtrip-1"},
    )
    assert replay.status_code == 200
    assert replay.json() == body
    assert len(_events(provisional_case)) == events_before

    detached = client.post(
        f"/api/v1/customers/{pan_id}/detach",
        json={"case_ids": [provisional_case], "reason": "owner said the invoice is a different buyer"},
        headers={"Idempotency-Key": "detach-roundtrip-1"},
    )
    assert detached.status_code == 200, detached.text[:800]
    assert detached.json()["moved_to"] == [provisional_id]
    assert _customer_id(provisional_case) == provisional_id, "detach restores the previous owner"

    types = [event.type for event in _events(provisional_case)]
    assert "customer.attach" in types and "customer.detach" in types
    verified = client.get(f"/api/v1/cases/{provisional_case}/events/verify")
    assert verified.status_code == 200 and verified.json()["valid"] is True

    restored = _profile(client, provisional_id)
    assert [invoice["case_id"] for invoice in restored["invoices"]] == [provisional_case]

    # And attaching again works: the round trip is not one-way.
    again = client.post(
        f"/api/v1/customers/{provisional_id}/attach",
        json={"target_customer_id": pan_id},
        headers={"Idempotency-Key": "attach-roundtrip-2"},
    )
    assert again.status_code == 200, again.text[:600]
    assert _customer_id(provisional_case) == pan_id


def test_attach_refuses_a_different_pan_and_needs_a_key(client):
    first_case = _create(client, gstin=PAN_GSTIN_A, name="Acme Industries Private Limited")
    second_case = _create(client, gstin=PAN_GSTIN_B, name="Acme Industries Pvt Ltd")
    first_id, second_id = _customer_id(first_case), _customer_id(second_case)

    refused = client.post(
        f"/api/v1/customers/{first_id}/attach",
        json={"target_customer_id": second_id},
        headers={"Idempotency-Key": "attach-pan-1"},
    )
    assert refused.status_code == 409, refused.text[:600]
    assert "never merged" in refused.json()["error"]["message"]

    missing_key = client.post(
        f"/api/v1/customers/{first_id}/attach",
        json={"target_customer_id": second_id},
    )
    assert missing_key.status_code == 400
    assert _customer_id(first_case) == first_id

    nothing = client.post(
        f"/api/v1/customers/{first_id}/detach",
        json={"case_ids": []},
        headers={"Idempotency-Key": "detach-empty-1"},
    )
    assert nothing.status_code == 422


def test_detach_can_separate_a_gstin_link(client):
    case = _create(client, gstin=PAN_GSTIN_A, name="Acme Industries Private Limited")
    customer_id = _customer_id(case)
    other = _customer_id(_create(client, gstin=INVALID_GSTIN, name="Other Buyer"))

    wrong = client.post(
        f"/api/v1/customers/{other}/detach",
        json={"gstin": PAN_GSTIN_A},
        headers={"Idempotency-Key": "detach-gstin-wrong"},
    )
    assert wrong.status_code == 422, wrong.text[:600]

    detached = client.post(
        f"/api/v1/customers/{customer_id}/detach",
        json={"gstin": PAN_GSTIN_A},
        headers={"Idempotency-Key": "detach-gstin-1"},
    )
    assert detached.status_code == 200, detached.text[:600]
    assert detached.json()["gstins"] == [PAN_GSTIN_A]
    assert _profile(client, customer_id)["gstins"] == []
    assert "customer.gstin_detached" in [event.type for event in _events(case)]


# ---------------------------------------------------------- suggestions ----


def test_a_dismissed_suggestion_stays_dismissed(client):
    pan_case = _create(
        client, gstin=PAN_GSTIN_A, name="Dismiss Buyer Private Limited"
    )
    provisional_case = _create(
        client, gstin=INVALID_GSTIN, name="Dismiss Buyer Pvt Ltd"
    )
    pan_id = _customer_id(pan_case)
    provisional_id = _customer_id(provisional_case)

    before = client.get("/api/v1/customers/suggestions")
    assert before.status_code == 200, before.text[:600]
    pairs = {(item["a"], item["b"], item["kind"]) for item in before.json()["suggestions"]}
    assert (provisional_id, pan_id, "ATTACH") in pairs
    assert before.json()["threshold"] == "0.90"

    dismissed = client.post(
        "/api/v1/customers/suggestions/dismiss",
        json={"a": provisional_id, "b": pan_id},
        headers={"Idempotency-Key": "dismiss-1"},
    )
    assert dismissed.status_code == 200, dismissed.text[:600]
    assert dismissed.json()["dismissed"] is True

    after = client.get("/api/v1/customers/suggestions")
    still_offered = {(item["a"], item["b"]) for item in after.json()["suggestions"]}
    assert (provisional_id, pan_id) not in still_offered
    assert (pan_id, provisional_id) not in still_offered

    replay = client.post(
        "/api/v1/customers/suggestions/dismiss",
        json={"a": pan_id, "b": provisional_id},
        headers={"Idempotency-Key": "dismiss-1"},
    )
    assert replay.status_code == 409, "the same key with a different body is a conflict"

    # Neither customer moved or changed identity: a dismissal is not a merge.
    assert _customer_row(provisional_case).id == provisional_id
    assert _profile(client, provisional_id)["stats"]["invoice_count"] == 1

    types = [event.type for event in _events(provisional_case)]
    assert "customer.merge_dismissed" in types


def test_undo_dismiss_brings_the_suggestion_back(client):
    pan_case = _create(client, gstin=PAN_GSTIN_A, name="Undo Buyer Private Limited")
    provisional_case = _create(client, gstin=INVALID_GSTIN, name="Undo Buyer Pvt Ltd")
    pan_id = _customer_id(pan_case)
    provisional_id = _customer_id(provisional_case)

    dismissed = client.post(
        "/api/v1/customers/suggestions/dismiss",
        json={"a": provisional_id, "b": pan_id},
        headers={"Idempotency-Key": "undo-dismiss-1"},
    )
    assert dismissed.status_code == 200, dismissed.text[:600]

    undone = client.post(
        "/api/v1/customers/suggestions/undo-dismiss",
        json={"a": pan_id, "b": provisional_id},
        headers={"Idempotency-Key": "undo-dismiss-2"},
    )
    assert undone.status_code == 200, undone.text[:600]
    body = undone.json()
    assert body["dismissed"] is False
    assert sorted((body["a"], body["b"])) == sorted((pan_id, provisional_id))

    offered = client.get("/api/v1/customers/suggestions").json()["suggestions"]
    assert any({item["a"], item["b"]} == {provisional_id, pan_id} for item in offered)

    types = [event.type for event in _events(provisional_case)]
    assert "customer.merge_dismissed" in types
    assert "customer.merge_dismissal_undone" in types

    # Undoing again is a no-op, not an error.
    again = client.post(
        "/api/v1/customers/suggestions/undo-dismiss",
        json={"a": provisional_id, "b": pan_id},
        headers={"Idempotency-Key": "undo-dismiss-3"},
    )
    assert again.status_code == 200
    assert "not dismissed" in again.json()["note"]


def test_gstin_attach_and_remove_are_audited(client):
    case = _create(client, gstin=PAN_GSTIN_A, name="Two States Private Limited")
    customer_id = _customer_id(case)
    second_state = "27" + PAN_GSTIN_A[2:]  # same PAN, different state code

    added = client.post(
        f"/api/v1/customers/{customer_id}/gstins",
        json={"gstin": second_state},
        headers={"Idempotency-Key": "gstin-add-1"},
    )
    assert added.status_code == 200, added.text[:600]
    assert added.json()["gstins"] == sorted([PAN_GSTIN_A, second_state])
    assert "customer.gstin_attached" in [event.type for event in _events(case)]

    removed = client.request(
        "DELETE",
        f"/api/v1/customers/{customer_id}/gstins/{second_state}",
        headers={"Idempotency-Key": "gstin-remove-1"},
    )
    assert removed.status_code == 200, removed.text[:600]
    assert removed.json()["gstins"] == [PAN_GSTIN_A]
    assert "customer.gstin_detached" in [event.type for event in _events(case)]

    # A GSTIN that carries another PAN is refused: never merged, group instead.
    refused = client.post(
        f"/api/v1/customers/{customer_id}/gstins",
        json={"gstin": PAN_GSTIN_B},
        headers={"Idempotency-Key": "gstin-add-2"},
    )
    assert refused.status_code == 409
    assert "different PAN" in refused.json()["error"]["message"]

    missing_key = client.post(
        f"/api/v1/customers/{customer_id}/gstins", json={"gstin": second_state}
    )
    assert missing_key.status_code == 400


def test_detach_can_undo_an_attach_by_naming_the_customer(client):
    provisional_case = _create(
        client, gstin=INVALID_GSTIN, name="Restore Buyer Pvt Ltd"
    )
    pan_case = _create(
        client, gstin=PAN_GSTIN_A, name="Restore Buyer Private Limited"
    )
    provisional_id = _customer_id(provisional_case)
    pan_id = _customer_id(pan_case)

    attached = client.post(
        f"/api/v1/customers/{provisional_id}/attach",
        json={"target_customer_id": pan_id},
        headers={"Idempotency-Key": "restore-attach-1"},
    )
    assert attached.status_code == 200, attached.text[:600]

    undone = client.post(
        f"/api/v1/customers/{pan_id}/detach",
        json={"restore_customer_id": provisional_id},
        headers={"Idempotency-Key": "restore-detach-1"},
    )
    assert undone.status_code == 200, undone.text[:600]
    assert undone.json()["moved_to"] == [provisional_id]
    assert undone.json()["case_ids"] == [provisional_case]
    assert _customer_id(provisional_case) == provisional_id

    nothing = client.post(
        f"/api/v1/customers/{pan_id}/detach",
        json={"restore_customer_id": provisional_id},
        headers={"Idempotency-Key": "restore-detach-2"},
    )
    assert nothing.status_code == 422
    assert "nothing was moved back" in nothing.json()["error"]["message"]


def test_linking_two_pans_as_a_group_removes_the_group_suggestion(client):
    first = _customer_id(
        _create(client, gstin=PAN_GSTIN_A, name="Groupable Traders Private Limited")
    )
    second = _customer_id(
        _create(client, gstin=PAN_GSTIN_B, name="Groupable Traders Pvt Ltd")
    )

    offered = client.get("/api/v1/customers/suggestions").json()["suggestions"]
    link_kinds = [
        item
        for item in offered
        if item["kind"] == "LINK_AS_GROUP" and {item["a"], item["b"]} == {first, second}
    ]
    assert link_kinds, f"expected a LINK_AS_GROUP suggestion, got {offered}"

    created = client.post(
        "/api/v1/customer-groups",
        json={"label": "Groupable group (synthetic)", "customer_ids": [first, second]},
        headers={"Idempotency-Key": "group-suggestion-1"},
    )
    assert created.status_code == 201, created.text[:600]

    offered_after = client.get("/api/v1/customers/suggestions").json()["suggestions"]
    assert not [
        item
        for item in offered_after
        if {item["a"], item["b"]} == {first, second}
    ]


# --------------------------------------------------- days, history, timing ----


def test_days_to_pay_run_from_acceptance_and_need_three_invoices(client):
    customer_case_ids = [
        _create(
            client,
            gstin=PAN_GSTIN_A,
            name="Timing Buyer Private Limited",
            principal="100000.00",
            days_since_delivery=days,
            invoice_no=f"INV-TIMING-{days}",
        )
        for days in (30, 40, 50)
    ]
    customer_id = _customer_id(customer_case_ids[0])
    for index, case_id in enumerate(customer_case_ids):
        _pay(client, case_id, "100000.00", key=f"timing-pay-{index}")

    # A second customer with two paid invoices: still not enough history.
    thin_case_ids = [
        _create(
            client,
            gstin=PAN_GSTIN_B,
            name="Thin History Pvt Ltd",
            principal="50000.00",
            days_since_delivery=days,
            invoice_no=f"INV-THIN-{days}",
        )
        for days in (10, 20)
    ]
    thin_id = _customer_id(thin_case_ids[0])
    for index, case_id in enumerate(thin_case_ids):
        _pay(client, case_id, "50000.00", key=f"thin-pay-{index}")

    profile = _profile(client, customer_id)
    stats = profile["stats"]
    assert stats["paid_count"] == 3
    assert stats["based_on"] == 3
    assert stats["avg_days_to_pay"] == "40.00"
    assert stats["median_days_to_pay"] == "40.00"
    assert stats["worst_days_to_pay"] == "50.00"
    assert stats["on_time_count"] == 2, (
        "the 50-day invoice was paid after the engine's legal due date (45 days)"
    )
    assert stats["on_time_text"] == "2 of 3 on time"
    assert stats["on_time_pct"] == "66.67"

    by_case = {point["case_id"]: point for point in profile["series"]}
    for case_id, days in zip(customer_case_ids, (30, 40, 50)):
        point = by_case[case_id]
        assert point["status"] == "PAID"
        assert point["days_to_pay"] == days
        invoice = next(item for item in profile["invoices"] if item["case_id"] == case_id)
        # Days are measured from acceptance (delivery), never from the invoice date.
        assert date.fromisoformat(point["accepted_on"]) == _today() - timedelta(days=days)
        assert date.fromisoformat(invoice["invoice_date"]) < date.fromisoformat(
            point["accepted_on"]
        )

    thin = _profile(client, thin_id)["stats"]
    assert thin["paid_count"] == 2
    assert thin["avg_days_to_pay"] is None
    assert "Not enough history" in thin["avg_days_to_pay_reason"]
    assert thin["based_on"] < thin["min_history"]

    ordered = _entries(client, sort="avg_days")
    assert ordered[0]["customer"]["id"] == customer_id
    assert ordered[-1]["customer"]["stats"]["avg_days_to_pay"] is None


def test_a_profile_carries_the_three_buyer_cost_lines_separately(client):
    case_id = _create(
        client,
        gstin=PAN_GSTIN_A,
        name="Buyer Cost Private Limited",
        principal="500000.00",
        days_since_delivery=120,
    )
    profile = _profile(client, _customer_id(case_id))
    summary = profile["buyer_cost_summary"]
    assert summary is not None
    assert [line["id"] for line in summary["lines"]] == [
        "PERMANENT_LOSS",
        "DEFERRAL",
        "DISCLOSURE",
    ]
    assert "never added together" in summary["note"]
    assert not any("total" in key.lower() for key in summary), (
        "the buyer's costs must never be combined into one total"
    )

    # The permanent-loss line is the engine's own accrued interest.
    detail = client.get(f"/api/v1/cases/{case_id}").json()
    interest = detail["latest_evaluation"]["financials"]["interest_total"]
    assert summary["lines"][0]["amount"] == interest


# -------------------------------------------------------------- insights ----


def _assert_insight_shapes(payload: dict) -> None:
    for field in (
        "outstanding_total",
        "overdue_total",
        "paid_total",
        "interest_accrued_now",
    ):
        assert isinstance(payload[field], str), f"{field} must be a decimal string"
    assert isinstance(payload["based_on"], int)
    assert payload["min_history"] >= 1
    for field in payload:
        assert not any(
            word in field.lower()
            for word in ("score", "rating", "risk", "rank", "defaulter", "blacklist")
        ), f"{field} labels the buyer instead of describing the book"


def test_insights_shape_and_wording(client):
    overdue_case = _create(
        client,
        gstin=INVALID_GSTIN,
        name="Overdue Insight Buyer",
        principal="400000.00",
        days_since_delivery=120,
    )
    _create(
        client,
        gstin=INVALID_GSTIN_B,
        name="Not Due Insight Buyer",
        principal="200000.00",
        days_since_delivery=1,
    )

    response = client.get("/api/v1/insights")
    assert response.status_code == 200, response.text[:800]
    payload = response.json()
    _assert_insight_shapes(payload)

    assert payload["as_of"] == _today().isoformat()
    assert payload["customer_count"] == 2
    assert payload["invoice_count"] == 2
    assert payload["avg_days_to_pay"] is None
    assert "Not enough history" in payload["avg_days_to_pay_reason"]
    assert payload["cash_in_estimate"] is None
    assert "switched off" in payload["cash_in_estimate_note"]
    assert payload["concentration_note"]
    # Assumptions are only added when a fallback was actually used; the field is
    # always present so the UI can render the drawer either way.
    assert isinstance(payload["assumptions"], list)

    # Only open, overdue invoices reach the 43B(h) list, with the exact wording.
    assert [item["case_id"] for item in payload["before_march"]] == [overdue_case]
    assert (
        payload["before_march"][0]["note"]
        == "43B(h): their deduction for this amount depends on payment"
    )
    assert payload["before_march"][0]["next_march"] == "2027-03-31"

    # The concentration chart is the same money as the total, not a new figure.
    chart = sum(
        (Decimal(point["value"]) for point in payload["outstanding_by_customer"]),
        Decimal("0.00"),
    )
    assert chart == Decimal(payload["outstanding_total"])

    # A list row and the profile agree with the portfolio view.
    entries = _entries(client)
    total = sum(
        (Decimal(entry["customer"]["stats"]["outstanding_total"]) for entry in entries),
        Decimal("0.00"),
    )
    assert total == Decimal(payload["outstanding_total"])


# --------------------------------------------------- the frozen surfaces ----


def test_the_v1_and_v1_1_surfaces_still_answer(client):
    evaluated = client.post("/api/v1/evaluate-case", json=PRESET)
    assert evaluated.status_code == 200, evaluated.text[:400]
    assert evaluated.json()["contract_version"] == "1.0"

    listed = client.get("/api/v1/cases")
    assert listed.status_code == 200
    assert set(listed.json()) == {"cases", "count"}

    created = client.post("/api/v1/cases", json=_request(gstin=INVALID_GSTIN, name="Frozen Surfaces"))
    assert created.status_code == 201
    assert set(created.json()) == {"case", "latest_evaluation", "active_track", "available_actions"}
    assert created.json()["latest_evaluation"]["contract_version"] == "1.0"
