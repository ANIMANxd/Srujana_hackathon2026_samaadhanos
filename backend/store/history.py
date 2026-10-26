"""Deterministic 12-month synthetic customer history (`make seed-history`).

The rows are generated as a CSV and pushed through the **real import route**
(`POST /api/v1/import/invoices`, preview then commit), so seeding exercises the
same parsing, customer resolution, engine evaluation and payment recording an
owner's upload does. Nothing is written straight to the tables.

Six fictional buyers, one fixed random seed, so the same day produces the same
file byte for byte:

- a prompt payer (paid inside the engine's legal due date),
- a chronic late payer (about 70 days on average, with open overdue invoices),
- one legal entity with a Karnataka and a Tamil Nadu GSTIN (same PAN, so the
  book groups them automatically),
- a name-only provisional that is a near-duplicate of the prompt payer, which
  becomes an ATTACH suggestion,
- two related companies with different PANs and near-identical names, which
  becomes a LINK_AS_GROUP suggestion (never a merge).

GSTINs are format-valid and fictional, names are obviously invented, and every
contact number is `+91 90000 0000x` (synthetic). No real party, Udyam number or
GSTIN appears here (AGENTS.md rule 11).

Dates are laid out relative to the day the seed runs, because the engine prices a
delay against the calculation date; the *offsets*, amounts, payment delays and
invoice numbers are fixed by the seed constant. The plan is twelve months, but the
oldest delivery is compressed into the window the captured Bank Rate epochs can
price (s.16 interest cannot be computed before the first epoch: CR-8). On today's
config that window is about eight months and it widens to the full twelve as soon
as V1 fills the earlier epochs, with no change here. Nothing is ever priced at a
rate the config has not captured.

The v4 presets are untouched: `make db-reset` seeds them first and then calls this
function, and the import's own duplicate rule makes a second run a no-op.
`make seed-history` rebuilds the store with this history only.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence

from fastapi import UploadFile

from backend.app import deps
from backend.store import db as store_db

# One fixed seed for every synthetic choice. Changing it changes the demo book.
SEED = 20261026
HISTORY_FILENAME = "invoice_history_12m.csv"
CONTACT_PREFIX = "+91 90000 0000"

HEADER: tuple[str, ...] = (
    "invoice_no",
    "invoice_date",
    "delivery_date",
    "amount",
    "buyer_name",
    "buyer_gstin",
    "agreed_credit_days",
    "paid_on",
    "paid_amount",
    "notes",
)


@dataclass(frozen=True)
class HistoryCustomer:
    """One fictional buyer and the invoice plan behind it.

    `rows` is `(days_before_today_for_delivery, days_after_delivery_paid, amount)`
    with `None` as the paid delay for an invoice that is still open.
    """

    key: str
    label: str
    name: str
    phone: str
    gstins: tuple[str, ...]
    credit_days: str
    rows: tuple[tuple[int, int | None, str], ...]
    note: str

    def gstin_for(self, index: int) -> str:
        if not self.gstins:
            return ""
        return self.gstins[(index - 1) % len(self.gstins)]


# ---------------------------------------------------------------- the book ----
# Every GSTIN is format-valid (2 digits, 5 letters, 4 digits, 1 letter, 1, Z,
# 1) and fabricated; the PAN inside it is what makes two states one entity.

HISTORY_CUSTOMERS: tuple[HistoryCustomer, ...] = (
    HistoryCustomer(
        key="GPW",
        label="prompt payer",
        name="Ganga Precision Works Private Limited",
        phone=f"{CONTACT_PREFIX}1",
        gstins=("29AABCG1234H1Z5",),  # Karnataka
        credit_days="45",
        rows=(
            (340, 24, "240000"),
            (305, 31, "185000"),
            (270, 18, "320000"),
            (235, 40, "96000"),
            (200, 27, "410000"),
            (165, 33, "157500"),
            (130, 21, "275000"),
            (100, 29, "128000"),
            (70, 36, "208000"),
            (25, None, "95000"),
        ),
        note="Pays inside the legal due date; one invoice is not due yet.",
    ),
    HistoryCustomer(
        key="YST",
        label="chronic late payer",
        name="Yamuna Steel Traders Pvt Ltd",
        phone=f"{CONTACT_PREFIX}2",
        gstins=("29AABCY5678J1Z3",),  # Karnataka
        credit_days="45",
        rows=(
            (335, 62, "350000"),
            (300, 68, "420000"),
            (265, 71, "285000"),
            (230, 74, "510000"),
            (195, 75, "390000"),
            (160, None, "1250000"),
            (120, None, "640000"),
            (85, None, "875000"),
        ),
        note="Averages about 70 days; three invoices are still open and overdue.",
    ),
    HistoryCustomer(
        key="KAC",
        label="same PAN in two states",
        name="Kaveri Auto Components Private Limited",
        phone=f"{CONTACT_PREFIX}3",
        gstins=("29AABCK9012L1Z7", "33AABCK9012L1Z4"),  # Karnataka + Tamil Nadu
        credit_days="45",
        rows=(
            (300, 38, "265000"),
            (265, 44, "310000"),
            (230, 47, "180000"),
            (195, 41, "225000"),
            (160, 39, "195000"),
            (120, None, "450000"),
            (45, None, "320000"),
        ),
        note="Two state registrations, one PAN, so the book keeps them as one customer.",
    ),
    HistoryCustomer(
        key="GPX",
        label="provisional near-duplicate",
        name="Ganga Precision Works Pvt Ltd",
        phone=f"{CONTACT_PREFIX}4",
        gstins=(),  # no GSTIN at all: a name-only provisional record
        credit_days="45",
        rows=(
            (250, 64, "185000"),
            (205, 69, "240000"),
            (160, 71, "132000"),
            (120, None, "168000"),
            (55, None, "210000"),
        ),
        note="No GSTIN on the invoice, and the name is close to the prompt payer's.",
    ),
    HistoryCustomer(
        key="SPM",
        label="related company (Maharashtra)",
        name="Saraswati Polymers Private Limited",
        phone=f"{CONTACT_PREFIX}5",
        gstins=("27AABCS3456M1Z9",),  # Maharashtra
        credit_days="45",
        rows=(
            (320, 50, "275000"),
            (280, 55, "340000"),
            (240, 48, "198000"),
            (200, 60, "412000"),
            (150, None, "230000"),
            (90, None, "360000"),
        ),
        note="Similar name to the Karnataka company; different PAN, so never merged.",
    ),
    HistoryCustomer(
        key="SPK",
        label="related company (Karnataka)",
        name="Saraswati Polymers Pvt Ltd",
        phone=f"{CONTACT_PREFIX}6",
        gstins=("29AABCS3456N1Z2",),  # Karnataka
        credit_days="45",
        rows=(
            (300, 52, "210000"),
            (250, 58, "295000"),
            (200, 61, "175000"),
            (140, None, "260000"),
            (80, None, "330000"),
        ),
        note="Related to the Maharashtra company by name only; link them as a group.",
    ),
)

HISTORY_ROW_COUNT = sum(len(customer.rows) for customer in HISTORY_CUSTOMERS)
HISTORY_GSTINS: tuple[str, ...] = tuple(
    gstin for customer in HISTORY_CUSTOMERS for gstin in customer.gstins
)


# ---------------------------------------------------------------- building ----


def indian_amount(value: Decimal) -> str:
    """`125000` -> `1,25,000.00`, the grouping the import accepts and an owner expects."""
    text = format(value.quantize(Decimal("0.01")), "f")
    whole, _, paise = text.partition(".")
    if len(whole) <= 3:
        return f"{whole}.{paise}"
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) + f".{paise}"


def earliest_priceable_delivery() -> date | None:
    """The oldest delivery the captured Bank Rate epochs can price.

    The ledger starts on the appointed day (delivery + 45 + 1 with the s.15 cap),
    and `engine.config.bank_rate_on` refuses a day before the first captured
    epoch (CR-8). This reads that epoch from the config instead of hard-coding a
    date, so adding the earlier epochs (V1) widens the demo window with no code
    change. Returns None when the config has no epochs at all.
    """
    from backend.app.config_loader import load_config

    entry = load_config().get("bank_rate_epochs")
    value = entry.get("value") if isinstance(entry, dict) else None
    starts = [
        date.fromisoformat(str(item["from"]))
        for item in (value or [])
        if isinstance(item, dict) and item.get("from")
    ]
    if not starts:
        return None
    return min(starts) - timedelta(days=46)


def _window(as_of: date, floor: date | None) -> tuple[date, float]:
    """Oldest delivery for the book, and the scale applied to the 12-month plan."""
    planned_days = max(offset for customer in HISTORY_CUSTOMERS for offset, _, _ in customer.rows)
    oldest = as_of - timedelta(days=planned_days)
    if floor is not None and oldest < floor:
        oldest = floor
    span = max((as_of - oldest).days, 1)
    return oldest, min(span / planned_days, 1.0)


def build_history(as_of: date, *, floor: date | None = None) -> str:
    """The whole CSV, deterministic for a given `as_of`.

    Offsets are scaled into the window the captured Bank Rate epochs can price
    (`_window`). On today's config that is the oldest priceable delivery, so the
    book is as long as the law-as-configured allows; when V1 fills the earlier
    epochs the same plan reaches the full twelve months. `floor` is injectable so
    a test can pin the window without reading the config.
    """
    if floor is None:
        floor = earliest_priceable_delivery()
    oldest, scale = _window(as_of, floor)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for customer in HISTORY_CUSTOMERS:
        for index, (offset, paid_delay, amount) in enumerate(customer.rows, start=1):
            delivery = max(as_of - timedelta(days=round(offset * scale)), oldest)
            invoice = delivery + timedelta(days=1)
            paid_on = ""
            paid_amount = ""
            if paid_delay is not None:
                paid_on_date = min(delivery + timedelta(days=paid_delay), as_of)
                paid_on = paid_on_date.isoformat()
                paid_amount = indian_amount(Decimal(amount))
            notes = ""
            if index == 1:
                notes = f"Contact {customer.phone} (synthetic). {customer.note}"
            writer.writerow(
                [
                    f"{customer.key}/{as_of.year}/{index:03d}",
                    invoice.isoformat(),
                    delivery.isoformat(),
                    indian_amount(Decimal(amount)),
                    customer.name,
                    customer.gstin_for(index),
                    customer.credit_days,
                    paid_on,
                    paid_amount,
                    notes,
                ]
            )
    return buffer.getvalue()


# ----------------------------------------------------------------- seeding ----


@dataclass(frozen=True)
class SeedReport:
    """What one seed run did, for the Makefile output and the tests."""

    rows: int
    created_cases: int
    payments: int
    skipped: int
    invalid: int
    customers: int


async def _import(raw: bytes, *, mode: str, token: str | None):
    """Call the real route function, exactly as an upload would."""
    from backend.app.routes.imports import import_invoices

    upload = UploadFile(io.BytesIO(raw), filename=HISTORY_FILENAME)
    return await import_invoices(
        file=upload, mode=mode, import_token=token, x_import_token=None
    )


def _visible_customers() -> int:
    """Customers with at least one invoice: what `GET /customers` lists."""
    from sqlmodel import select

    from backend.store.models import Case

    with store_db.session_scope() as session:
        return len(
            {row.customer_id for row in session.exec(select(Case)).all() if row.customer_id}
        )


def seed_history(
    *, as_of: date | None = None, reset: bool = False, url: str | None = None
) -> SeedReport:
    """Seed the 12-month history through the import path.

    `reset=True` deletes the database file first (the `make seed-history` mode:
    the book is then exactly the six seeded customers). Without it the seed is
    additive and idempotent, which is what `make db-reset` uses after the presets.
    """
    target = url or store_db.database_url()
    store_db.dispose()
    if reset:
        path = store_db.database_file(target)
        if path is not None and path.exists():
            path.unlink()
    store_db.init_db(target)

    today = as_of or deps.get_adapters().clock.now().date()
    raw = build_history(today).encode("utf-8")

    preview = asyncio.run(_import(raw, mode="preview", token=None))
    commit = asyncio.run(_import(raw, mode="commit", token=preview.import_token))

    return SeedReport(
        rows=preview.summary.total_rows,
        created_cases=commit.summary.created_rows,
        payments=commit.summary.payments_created,
        skipped=commit.summary.skipped_rows,
        invalid=commit.summary.invalid_rows,
        customers=_visible_customers(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """`make seed-history`: rebuild the store with the 12-month history only."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.store.history",
        description=(
            "Seed a deterministic 12-month synthetic customer history through the "
            "CSV import. Demo data only."
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the database first (what `make seed-history` does)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="layout the invoices against this date (YYYY-MM-DD); default is today",
    )
    args = parser.parse_args(argv)

    report = seed_history(
        as_of=date.fromisoformat(args.as_of) if args.as_of else None,
        reset=args.reset,
    )
    if args.reset:
        print(f"recreated {store_db.database_file() or store_db.database_url()}")
    else:
        print("store kept")
    floor = earliest_priceable_delivery()
    window_end = date.fromisoformat(args.as_of) if args.as_of else deps.get_adapters().clock.now().date()
    if floor is not None:
        print(f"history window: {max(window_end - timedelta(days=365), floor)} to {window_end} (12-month plan, clamped to the captured Bank Rate epochs)")
    print(
        f"imported {report.rows} CSV row(s): {report.created_cases} case(s), "
        f"{report.payments} payment(s) via POST /api/v1/import/invoices"
    )
    if report.skipped or report.invalid:
        print(f"  skipped {report.skipped} duplicate row(s), {report.invalid} invalid row(s)")
    print(f"customer book: {report.customers} customer(s); expect one ATTACH and one LINK_AS_GROUP suggestion")
    return 0 if report.invalid == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
