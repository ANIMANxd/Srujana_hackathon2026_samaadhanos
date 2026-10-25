"""Seed the demo presets into the store (`make db-reset`).

Every preset in `backend/presets/*.json` becomes one `cases` row with the engine
input stored **verbatim** in `input_json`, so anything the engine later says about
it is reproducible from the row alone.

Ids are deterministic ULIDs derived from the preset id and the preset's own
`calculation_date`, so re-seeding produces the same ids and demo links stay valid.
Nothing here invents a legal number: `accepted_amount` is the preset's
`transaction.principal`, and no evaluation is stored until a case is actually
evaluated.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlalchemy.orm import Session

from backend.store import db as _db
from backend.store.ids import deterministic_ulid
from backend.store.models import Case, Event

PRESETS_DIR = Path(__file__).resolve().parents[1] / "presets"

# Fixed at 09:00 UTC on the preset's own calculation date: stable across runs.
_SEED_HOUR = time(9, 0, tzinfo=UTC)


def preset_files() -> list[Path]:
    """Every preset file, sorted, so the seed order is stable."""
    return sorted(PRESETS_DIR.glob("*.json"))


def _invoice_ref(request: dict[str, Any], preset_id: str) -> str:
    """The invoice number if the preset names one, else a labelled stand-in.

    Presets carry no `invoice_no` field, so the evidence reference is the only
    real source. The fallback is clearly synthetic and never presented as a
    document number.
    """
    for item in request.get("evidence", {}).get("items", []) or []:
        if str(item.get("kind", "")).upper() == "INVOICE" and item.get("ref"):
            return str(item["ref"])
    return f"{preset_id}/INV"


def _supplier_ref(request: dict[str, Any], preset_id: str) -> str:
    supplier = request.get("supplier") or {}
    return str(supplier.get("udyam_number") or supplier.get("name") or preset_id)


def case_from_preset(preset_id: str, document: dict[str, Any]) -> Case:
    """Build the `cases` row for one preset document."""
    request = document.get("request") or {}
    transaction = request.get("transaction") or {}
    buyer = request.get("buyer") or {}

    calculation_date = transaction.get("calculation_date")
    seeded_at = (
        datetime.combine(datetime.fromisoformat(str(calculation_date)).date(), _SEED_HOUR)
        if calculation_date
        else datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    )

    invoice_date = transaction.get("invoice_date")
    if not invoice_date:
        raise ValueError(f"preset {preset_id!r} has no transaction.invoice_date")

    return Case(
        id=deterministic_ulid(f"preset:{preset_id}", seeded_at),
        supplier_ref=_supplier_ref(request, preset_id),
        buyer_gstin=buyer.get("gstin"),
        invoice_no=_invoice_ref(request, preset_id),
        invoice_date=datetime.fromisoformat(str(invoice_date)).date(),
        accepted_amount=Decimal(str(transaction.get("principal", "0.00"))),
        delivery_date=(
            datetime.fromisoformat(str(transaction["delivery_date"])).date()
            if transaction.get("delivery_date")
            else None
        ),
        input_json=request,
        engine_version="1.0",
        config_version="1.0",
        created_at=seeded_at,
    )


def seed_presets(session: Session, *, replace: bool = True) -> list[Case]:
    """Insert every preset as a case, each with an opening audit event.

    The event is what makes `GET /cases/{id}/events` and the judge console's "verify
    chain" meaningful for demo data: a preset-shaped case should not look like it
    appeared from nowhere.
    """
    from backend.store import audit

    seeded: list[Case] = []
    for path in preset_files():
        document = json.loads(path.read_text(encoding="utf-8"))
        case = case_from_preset(path.stem, document)
        existing = session.get(Case, case.id)
        if existing is not None:
            if not replace:
                seeded.append(existing)
                continue
            # Re-seeding a case must also clear its chain, or the new "case.created"
            # event would link to a previous run's hash and seq 1 would not exist.
            for stale in session.exec(
                select(Event).where(Event.case_id == case.id)
            ).all():
                session.delete(stale)
            session.delete(existing)
            session.flush()
        session.add(case)
        session.flush()
        audit.append_event(
            session,
            case_id=case.id,
            type="case.created",
            payload={"invoice_no": case.invoice_no, "source": "preset", "preset_id": path.stem},
            actor="SYSTEM",
            created_at=case.created_at,
        )
        seeded.append(case)
    session.flush()
    return seeded


def reset_and_seed(url: str | None = None) -> list[Case]:
    """Delete the database file, recreate every table, and seed the presets."""
    target = url or _db.database_url()
    _db.dispose()

    path = _db.database_file(target)
    if path is not None and path.exists():
        path.unlink()

    _db.init_db(target)
    with _db.session_scope() as session:
        return seed_presets(session)


def seeded_case_ids(url: str | None = None) -> dict[str, str]:
    """Preset id -> case id, for callers that need a stable demo mapping."""
    target = url or _db.database_url()
    _db.init_db(target)
    mapping: dict[str, str] = {}
    with _db.session_scope() as session:
        for path in preset_files():
            document = json.loads(path.read_text(encoding="utf-8"))
            case = case_from_preset(path.stem, document)
            row = session.exec(select(Case).where(Case.id == case.id)).first()
            if row is not None:
                mapping[path.stem] = row.id
    return mapping


def main() -> int:
    """`make db-reset`: delete the database, recreate it, seed the presets."""
    import sys

    target = _db.database_url()
    cases = reset_and_seed(target)
    path = _db.database_file(target)
    where = str(path) if path is not None else target
    print(f"recreated {where}")
    print(f"seeded {len(cases)} preset case(s):")
    for case in sorted(cases, key=lambda c: c.created_at):
        print(f"  {case.id}  {case.invoice_no:14}  {case.accepted_amount:>14}  {case.input_json.get('case_id', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
