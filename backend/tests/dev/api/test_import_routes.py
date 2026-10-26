"""CSV import: preview writes nothing, commit reuses the case route, re-commit skips.

The tests check behaviour, not formulas: the engine numbers are the engine's, and
the import's job is to hand it the same request `POST /cases` would.
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
from backend.store.models import Case, Customer, Payment

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

HEADER = (
    "invoice_no,invoice_date,delivery_date,amount,buyer_name,buyer_gstin,"
    "agreed_credit_days,paid_on,paid_amount,notes"
)
VALID_GSTIN = "29ABCDE1234F1Z5"  # PAN ABCDE1234F
SAME_PAN_OTHER_STATE = "27ABCDE1234F1Z5"


def _today() -> date:
    return deps.get_adapters().clock.now().date()


def _iso(days_ago: int) -> str:
    return (_today() - timedelta(days=days_ago)).isoformat()


def _row(
    invoice_no: str,
    *,
    amount: str = "1,25,000.00",
    buyer: str = "Sri Lakshmi Traders",
    gstin: str = "",
    invoice_days: int = 80,
    delivery_days: int = 81,
    credit: str = "45",
    paid_on: str = "",
    paid_amount: str = "",
    notes: str = "",
) -> str:
    return (
        f"{invoice_no},{_iso(invoice_days)},{_iso(delivery_days)},\"{amount}\",{buyer},"
        f"{gstin},{credit},{paid_on},\"{paid_amount}\",{notes}"
    )


def _csv(*rows: str) -> bytes:
    return (HEADER + "\n" + "\n".join(rows) + "\n").encode("utf-8")


def _preview(client: TestClient, raw: bytes) -> dict:
    response = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )
    assert response.status_code == 200, response.text[:800]
    return response.json()


def _commit(client: TestClient, raw: bytes, token: str) -> dict:
    response = client.post(
        "/api/v1/import/invoices",
        params={"mode": "commit", "import_token": token},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )
    assert response.status_code == 200, response.text[:800]
    return response.json()


def _counts() -> dict[str, int]:
    with store_db.session_scope() as session:
        return {
            "cases": len(session.exec(select(Case)).all()),
            "customers": len(session.exec(select(Customer)).all()),
            "payments": len(session.exec(select(Payment)).all()),
        }


def test_preview_parses_and_stores_nothing(client):
    raw = _csv(
        _row("IMP-1"),
        _row("IMP-2", amount="48,500.00", paid_on=_iso(10), paid_amount="48,500.00"),
    )

    body = _preview(client, raw)

    assert body["mode"] == "preview"
    assert body["import_token"]
    assert body["summary"]["total_rows"] == 2
    assert body["summary"]["valid_rows"] == 2
    assert body["summary"]["date_format"] == "YYYY-MM-DD"
    first = body["rows"][0]
    assert first["row_no"] == 2, "the CSV header is row 1"
    assert first["status"] == "VALID"
    assert first["parsed"]["invoice_no"] == "IMP-1"
    assert first["parsed"]["amount"] == "125000.00"
    assert first["customer_match"]["would_create"] is True
    assert first["customer_match"]["matched_on"] == "NEW"
    assert body["rows"][1]["parsed"]["paid_amount"] == "48500.00"

    assert _counts() == {"cases": 0, "customers": 0, "payments": 0}, (
        "a preview must not create customers, cases or payments"
    )


def test_commit_creates_cases_and_payments(client):
    raw = _csv(
        _row("IMP-10", gstin=VALID_GSTIN),
        _row(
            "IMP-11",
            amount="50,000.00",
            buyer="Nandi Components Pvt Ltd",
            paid_on=_iso(12),
            paid_amount="50,000.00",
        ),
    )
    token = _preview(client, raw)["import_token"]

    body = _commit(client, raw, token)

    assert body["mode"] == "commit"
    assert body["summary"]["created_rows"] == 2
    assert body["summary"]["payments_created"] == 1
    assert len(body["created_case_ids"]) == 2
    assert [row["status"] for row in body["rows"]] == ["CREATED", "CREATED"]
    assert _counts() == {"cases": 2, "customers": 2, "payments": 1}

    # The paid row's payment is on the case, through the normal payment route.
    paid_case = body["rows"][1]["case_id"]
    history = client.get(f"/api/v1/cases/{paid_case}/payments").json()
    assert history["count"] == 1
    assert history["payments"][0]["amount"] == "50000.00"
    assert history["payments"][0]["method"] == "other"
    assert history["payments"][0]["paid_on"] == _iso(12)

    # The case went through POST /cases, so the engine and the customer ran.
    detail = client.get(f"/api/v1/cases/{body['created_case_ids'][0]}").json()
    assert detail["latest_evaluation"]["timeline"]["delivery_date"] == _iso(81)
    listed = client.get("/api/v1/customers").json()
    names = {entry["display_name"] for entry in listed["entries"]}
    assert {"Sri Lakshmi Traders", "Nandi Components Pvt Ltd"} <= names


def test_recommit_skips_duplicates(client):
    raw = _csv(_row("IMP-20"), _row("IMP-21", amount="9,000.00"))
    token = _preview(client, raw)["import_token"]
    first = _commit(client, raw, token)
    assert first["summary"]["created_rows"] == 2
    before = _counts()

    token_again = _preview(client, raw)["import_token"]
    again = _commit(client, raw, token_again)

    assert again["summary"]["created_rows"] == 0
    assert again["summary"]["skipped_rows"] == 2
    assert again["created_case_ids"] == []
    assert len(again["skipped"]) == 2
    assert _counts() == before, "a second commit must not duplicate cases or payments"

    # A duplicate is visible in the preview too, so the owner sees it first.
    rows = _preview(client, raw)["rows"]
    assert all(row["status"] == "DUPLICATE" for row in rows)
    assert "already in your book" in rows[0]["warnings"][0]


def test_malformed_rows_are_reported_not_fatal(client):
    bad_date = f"IMP-30,{_iso(50)},not-a-date,1000.00,Bad Date Ltd,,,,"
    bad_amount = f"IMP-31,{_iso(50)},{_iso(51)},1.2.3,Bad Amount Ltd,,,,"
    formula = f"IMP-32,{_iso(50)},{_iso(51)},\"=1+1\",Formula Ltd,,,,"
    no_buyer = f"IMP-33,{_iso(50)},{_iso(51)},1000.00,,,,,"
    no_invoice = f",{_iso(50)},{_iso(51)},1000.00,No Invoice Ltd,,,,"
    duplicate = _row("IMP-35", amount="1,000.00", buyer="Dup Ltd")
    raw = _csv(
        bad_date,
        bad_amount,
        formula,
        no_buyer,
        no_invoice,
        duplicate,
        duplicate,
        _row("IMP-36", amount="1,000.00", buyer="Good Row Ltd"),
    )

    body = _preview(client, raw)
    summary = body["summary"]
    assert summary["total_rows"] == 8
    assert summary["valid_rows"] == 2, "the first copy of the repeated invoice is usable"
    assert summary["invalid_rows"] == 5
    assert summary["duplicate_rows"] == 1, "the second copy is the duplicate"

    errors = {row["row_no"]: " ".join(row["errors"]) for row in body["rows"]}
    assert "not in this file's date format" in errors[2]
    assert "not a number" in errors[3]
    assert "formula" in errors[4]
    assert "buyer_name is required" in errors[5]
    assert "invoice_no is required" in errors[6]
    no_invoice_row = next(row for row in body["rows"] if row["row_no"] == 6)
    assert no_invoice_row["status"] == "INVALID"
    duplicate_row = next(row for row in body["rows"] if row["row_no"] == 8)
    assert duplicate_row["status"] == "DUPLICATE"
    assert "appears earlier in this file" in duplicate_row["warnings"][0]

    committed = _commit(client, raw, body["import_token"])
    assert committed["summary"]["created_rows"] == 2, "the good row and the first copy"
    assert committed["summary"]["invalid_rows"] == 5
    assert committed["summary"]["skipped_rows"] == 1
    assert _counts()["cases"] == 2, "malformed rows never become cases"


def test_indian_and_western_amount_formats_parse(client):
    raw = _csv(
        _row("IMP-40", amount="1,25,000.00"),
        _row("IMP-41", amount="12,34,567.50"),
        _row("IMP-42", amount="125000"),
        _row("IMP-43", amount="125,000.00"),
    )

    body = _preview(client, raw)

    assert [row["parsed"]["amount"] for row in body["rows"]] == [
        "125000.00",
        "1234567.50",
        "125000.00",
        "125000.00",
    ]
    assert all(isinstance(row["parsed"]["amount"], str) for row in body["rows"])


def test_dd_mm_yyyy_is_read_per_file(client):
    invoice = (_today() - timedelta(days=80)).strftime("%d-%m-%Y")
    delivery = (_today() - timedelta(days=81)).strftime("%d-%m-%Y")
    raw = _csv(f"IMP-50,{invoice},{delivery},5000.00,Date Buyer Ltd,,,,,")

    body = _preview(client, raw)

    assert body["summary"]["date_format"] == "DD-MM-YYYY"
    assert body["rows"][0]["parsed"]["invoice_date"] == _iso(80)


def test_a_file_that_mixes_date_formats_is_refused(client):
    invoice = (_today() - timedelta(days=80)).strftime("%d-%m-%Y")
    raw = _csv(
        _row("IMP-60"),
        f"IMP-61,{invoice},{_iso(81)},5000.00,Mixed Buyer Ltd,,,,,",
    )

    response = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )

    assert response.status_code == 422
    assert "mixes date formats" in response.json()["error"]["message"]
    assert _counts()["cases"] == 0


def test_commit_needs_the_token_from_the_same_file(client):
    raw = _csv(_row("IMP-70"))
    _preview(client, raw)

    missing = client.post(
        "/api/v1/import/invoices",
        params={"mode": "commit"},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )
    assert missing.status_code == 400
    assert "import_token" in missing.json()["error"]["message"]

    token = _preview(client, raw)["import_token"]
    other = _csv(_row("IMP-71"))
    wrong = client.post(
        "/api/v1/import/invoices",
        params={"mode": "commit", "import_token": token},
        files={"file": ("invoices.csv", other, "text/csv")},
    )
    assert wrong.status_code == 400
    assert "does not match the file" in wrong.json()["error"]["message"]
    assert _counts()["cases"] == 0

    # The header works as an alternative to the query parameter.
    ok = client.post(
        "/api/v1/import/invoices",
        params={"mode": "commit"},
        files={"file": ("invoices.csv", raw, "text/csv")},
        headers={"X-Import-Token": token},
    )
    assert ok.status_code == 200, ok.text[:600]
    assert ok.json()["summary"]["created_rows"] == 1


def test_customer_resolution_reuses_the_existing_book(client):
    created = client.post(
        "/api/v1/cases",
        json={
            **copy.deepcopy(PRESET),
            "buyer": {
                **PRESET["buyer"],
                "gstin": VALID_GSTIN,
                "name": "Acme Industries Private Limited",
            },
        },
    )
    assert created.status_code == 201, created.text[:600]
    existing = client.get("/api/v1/customers").json()["entries"][0]

    raw = _csv(
        _row("IMP-80", buyer="Acme Industries Private Limited", gstin=VALID_GSTIN),
        _row("IMP-81", buyer="Acme Industries Private Limited", gstin=SAME_PAN_OTHER_STATE),
        _row("IMP-82", buyer="Acme Industries", gstin=""),
    )
    rows = _preview(client, raw)["rows"]

    assert rows[0]["customer_match"]["matched_on"] == "GSTIN"
    assert rows[0]["customer_match"]["customer_id"] == existing["id"]
    assert rows[0]["customer_match"]["would_create"] is False
    assert rows[1]["customer_match"]["matched_on"] == "PAN"
    assert rows[1]["customer_match"]["customer_id"] == existing["id"]
    assert rows[2]["customer_match"]["would_create"] is True


def test_limits_and_bad_files(client):
    # Not UTF-8.
    broken = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", b"\xff\xfe\x00broken", "text/csv")},
    )
    assert broken.status_code == 422
    assert "UTF-8" in broken.json()["error"]["message"]

    # Header missing a required column.
    no_header = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", b"invoice_no,amount\nIMP-1,100\n", "text/csv")},
    )
    assert no_header.status_code == 422
    assert "required columns" in no_header.json()["error"]["message"]

    # More than 2,000 data rows.
    many = _csv(*[_row(f"IMP-{index}", amount="1,000.00") for index in range(1, 2_002)])
    too_many = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", many, "text/csv")},
    )
    assert too_many.status_code == 422
    assert "limit is 2000" in too_many.json()["error"]["message"]

    # Over 2 MB.
    huge = HEADER.encode() + b"\n" + (b"x" * (2 * 1024 * 1024 + 10))
    too_big = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", huge, "text/csv")},
    )
    assert too_big.status_code == 413
    assert "larger than" in too_big.json()["error"]["message"]

    # A mode that does not exist is a validation error, not a silent preview.
    bad_mode = client.post(
        "/api/v1/import/invoices",
        params={"mode": "destroy"},
        files={"file": ("invoices.csv", _csv(_row("IMP-90")), "text/csv")},
    )
    assert bad_mode.status_code == 422
    assert _counts() == {"cases": 0, "customers": 0, "payments": 0}


def test_the_committed_demo_file_previews_cleanly(client):
    raw = (ROOT / "sample-data" / "invoice_history_demo.csv").read_bytes()

    body = _preview(client, raw)

    assert body["summary"]["invalid_rows"] == 0, body["summary"]
    assert body["summary"]["valid_rows"] == body["summary"]["total_rows"] == 8
    assert all(isinstance(row["parsed"]["amount"], str) for row in body["rows"])
    assert all(Decimal(row["parsed"]["amount"]) > 0 for row in body["rows"])
