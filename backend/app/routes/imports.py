"""CSV invoice-history import: preview and commit (contract v1.2).

This route is a **convenience around existing paths**, not a second engine:
`commit` builds a `CaseCreateRequest` per row and calls the same function
`POST /api/v1/cases` calls, so the gate, the dates, the interest ledger and the
customer attachment are identical. A payment row goes through the same payment
route as a manually recorded payment.

Two-phase on purpose:

- `?mode=preview` parses and checks every row, resolves the customer through
  `backend.insights.identity` and returns per-row errors and warnings. It writes
  nothing: no customer, no case, no payment, no staging row.
- `?mode=commit` needs the `import_token` from that preview **and the same file**,
  because the token signs the bytes. That keeps the commit stateless and proves
  the owner confirmed what they saw.

Idempotent on `(buyer_gstin or normalised buyer_name, invoice_no)`: a row whose
invoice is already in the book is skipped and reported, so a double click or a
re-sent file cannot duplicate cases. Nothing is sent anywhere and the file is
never written to disk.
"""

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlmodel import select

from backend.app import deps, imports
from backend.app.config_loader import load_config
from backend.app.routes import cases as case_routes
from backend.app.schemas_v4 import CaseCreateRequest
from backend.app.schemas_v5 import (
    ImportCommitResponse,
    ImportCustomerMatch,
    ImportParsedRow,
    ImportPreviewResponse,
    ImportRowResult,
    ImportSummary,
    PaymentCreateRequest,
    PaymentMethod,
)
from backend.insights.identity import (
    CustomerRecord,
    normalize_name,
    resolve as resolve_identity,
)
from backend.store import customers as customer_book
from backend.store.db import session_scope
from backend.store.ids import new_ulid
from backend.store.models import Case as CaseRow
from backend.store.models import Customer as CustomerRow
from backend.store.models import CustomerGstin

router = APIRouter(prefix="/api/v1", tags=["imports"])

IMPORT_NOTE = (
    "Preview writes nothing. Commit creates the cases through the same path as "
    "POST /cases, needs the token from the preview and the same file, and skips "
    "an invoice that is already in your book."
)

PAYMENT_NOTE = "Imported from CSV; the file has no payment method, so it is recorded as 'other'."


# ------------------------------------------------------------- customers ----


def _identity_records(session) -> list[CustomerRecord]:
    """Every customer as the pure resolver sees it. Read-only."""
    gstins: dict[str, list[str]] = {}
    for link in session.exec(select(CustomerGstin)).all():
        gstins.setdefault(link.customer_id, []).append(link.gstin)
    return [
        CustomerRecord(
            id=row.id,
            kind=row.kind,
            pan=row.pan,
            normalized_name=row.normalized_name,
            display_name=row.display_name,
            gstins=tuple(gstins.get(row.id, ())),
        )
        for row in session.exec(select(CustomerRow)).all()
    ]


def _match(row: imports.ParsedInvoice, records: list[CustomerRecord]) -> ImportCustomerMatch:
    """What CB1 would decide for this row, without writing anything."""
    decision = resolve_identity(row.buyer_gstin, row.buyer_name, records)
    matched_on = "NEW"
    if decision.customer_id is not None:
        gstin = (row.buyer_gstin or "").strip().upper()
        pan = decision.pan
        if gstin and any(gstin in record.gstins for record in records):
            matched_on = "GSTIN"
        elif pan and any(record.kind == "PAN" and record.pan == pan for record in records):
            matched_on = "PAN"
        else:
            matched_on = "NAME"
    display = None
    if decision.customer_id is not None:
        for record in records:
            if record.id == decision.customer_id:
                display = record.display_name
                break
    return ImportCustomerMatch(
        customer_id=decision.customer_id,
        display_name=display or (decision.display_name if decision.create else None),
        matched_on=matched_on,
        would_create=decision.create,
        warnings=list(decision.warnings),
    )


def _buyer_key(gstin: str | None, name: str | None, invoice_no: str) -> tuple[str, str, str]:
    """The idempotency key: a GSTIN when there is one, else the normalised name."""
    value = customer_book.normalize_gstin(gstin)
    if value:
        return ("gstin", value, invoice_no.strip().upper())
    return ("name", normalize_name(name), invoice_no.strip().upper())


def _existing_keys(session) -> dict[tuple[str, str, str], str]:
    """Invoices already in the book, keyed the same way an incoming row is."""
    found: dict[tuple[str, str, str], str] = {}
    for row in session.exec(select(CaseRow)).all():
        gstin, name = customer_book.case_buyer(row)
        key = _buyer_key(gstin, name, row.invoice_no)
        found.setdefault(key, row.id)
    return found


# -------------------------------------------------------------- defaults ----


def _defaults(session) -> tuple[dict[str, Any], str, str, list[str]]:
    """Supplier block, buyer tax rate and cost of capital for the imported cases.

    None of these is in the CSV. The owner's most recent case is the source when
    there is one; otherwise a labelled placeholder profile is used and every row
    carries a warning. Nothing statutory is invented: the tax rate falls back to
    the config's `tax_presets`, and the cost of capital to 0.
    """
    warnings: list[str] = []
    supplier: dict[str, Any] | None = None
    tax_rate: str | None = None
    cost_of_capital: str | None = None

    latest = session.exec(
        select(CaseRow).order_by(CaseRow.created_at.desc(), CaseRow.id.desc()).limit(1)
    ).first()
    if latest is not None and isinstance(latest.input_json, dict):
        payload = latest.input_json
        if isinstance(payload.get("supplier"), dict):
            supplier = dict(payload["supplier"])
        buyer = payload.get("buyer") if isinstance(payload.get("buyer"), dict) else {}
        if buyer.get("tax_rate_pct") is not None:
            tax_rate = str(buyer["tax_rate_pct"])
        if buyer.get("cost_of_capital_pct") is not None:
            cost_of_capital = str(buyer["cost_of_capital_pct"])

    if supplier is None:
        supplier = dict(imports.DEFAULT_SUPPLIER)

    if tax_rate is None:
        entry = load_config().get("tax_presets")
        value = entry.get("value") if isinstance(entry, dict) else None
        if isinstance(value, list) and value and isinstance(value[0], dict):
            tax_rate = str(value[0].get("tax_rate_pct") or "0.00")
        else:
            tax_rate = "0.00"
    if cost_of_capital is None:
        cost_of_capital = "0.00"

    warnings.append(imports.SUPPLIER_WARNING)
    return supplier, tax_rate, cost_of_capital, warnings


# ---------------------------------------------------------------- rows ----


def _parsed(row: imports.ParsedInvoice) -> ImportParsedRow | None:
    """The typed view of a row, only when it is complete enough to show one."""
    if not (
        row.invoice_no
        and row.invoice_date
        and row.delivery_date
        and row.amount is not None
        and row.buyer_name
    ):
        return None
    return ImportParsedRow(
        invoice_no=row.invoice_no,
        invoice_date=row.invoice_date,
        delivery_date=row.delivery_date,
        amount=row.amount,
        buyer_name=row.buyer_name,
        buyer_gstin=row.buyer_gstin,
        agreed_credit_days=row.agreed_credit_days,
        paid_on=row.paid_on,
        paid_amount=row.paid_amount,
        notes=row.notes,
    )


def _check_rows(
    parsed_rows: list[imports.ParsedInvoice],
    records: list[CustomerRecord],
    existing: dict[tuple[str, str, str], str],
) -> list[ImportRowResult]:
    """One verdict per row. Pure: no writes, no engine run."""
    results: list[ImportRowResult] = []
    seen: dict[tuple[str, str, str], int] = {}
    for row in parsed_rows:
        errors = list(row.errors)
        warnings = list(row.warnings)
        status = "INVALID" if errors else "VALID"
        match: ImportCustomerMatch | None = None

        if row.buyer_name:
            match = _match(row, records)
            warnings.extend(match.warnings)

        if not errors and row.invoice_no and row.buyer_name:
            key = _buyer_key(row.buyer_gstin, row.buyer_name, row.invoice_no)
            if key in existing:
                status = "DUPLICATE"
                warnings.append(
                    f"{row.invoice_no} is already in your book for this buyer; "
                    "commit will skip this row."
                )
            elif key in seen:
                status = "DUPLICATE"
                warnings.append(
                    f"{row.invoice_no} appears earlier in this file (row {seen[key]}); "
                    "commit will skip this row."
                )
            else:
                seen[key] = row.row_no

        results.append(
            ImportRowResult(
                row_no=row.row_no,
                status=status,
                parsed=_parsed(row),
                customer_match=match,
                errors=errors,
                warnings=warnings,
            )
        )
    return results


def _summary(
    results: list[ImportRowResult], fmt: str, file_warnings: list[str]
) -> ImportSummary:
    return ImportSummary(
        total_rows=len(results),
        valid_rows=sum(1 for item in results if item.status == "VALID"),
        invalid_rows=sum(1 for item in results if item.status == "INVALID"),
        duplicate_rows=sum(1 for item in results if item.status == "DUPLICATE"),
        date_format=fmt,
        warnings=list(file_warnings),
    )


async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    return raw


# -------------------------------------------------------------- routes ----


@router.post(
    "/import/invoices",
    response_model=ImportPreviewResponse | ImportCommitResponse,
)
async def import_invoices(
    file: UploadFile = File(..., description="UTF-8 CSV, header row required, max 2 MB / 2,000 rows."),
    mode: str = Query(default="preview", pattern="^(preview|commit)$"),
    import_token: str | None = Query(default=None),
    x_import_token: str | None = Header(default=None, alias="X-Import-Token"),
) -> ImportPreviewResponse | ImportCommitResponse:
    """Preview an invoice-history CSV, or commit the file you previewed.

    Columns: `invoice_no*, invoice_date*, delivery_date*, amount*, buyer_name*,
    buyer_gstin, agreed_credit_days, paid_on, paid_amount, notes`. Dates are
    `YYYY-MM-DD` or `DD-MM-YYYY` for the whole file; amounts may use Indian
    grouping (`1,25,000.00`). A cell starting with `=`, `+`, `-` or `@` is
    refused (CSV injection guard). Every error says which row and which column,
    in plain English.

    `preview` stores nothing at all. `commit` requires the token it returned plus
    the same bytes, creates each case through the same function `POST /cases`
    uses (so the engine runs per row and the customer is attached), records a
    payment when `paid_on` and `paid_amount` are present, and skips an invoice
    that is already in the book.
    """
    raw = await _read_upload(file)
    as_of = deps.get_adapters().clock.now().date()

    if mode == "commit":
        problem = imports.verify_token(
            import_token or x_import_token,
            raw,
            production=deps.is_production(),
        )
        if problem:
            raise HTTPException(status_code=400, detail=problem)

    try:
        parsed_rows, fmt, file_warnings = imports.read_rows(raw)
    except imports.ImportFileError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc

    with session_scope() as session:
        records = _identity_records(session)
        existing = _existing_keys(session)
        supplier, tax_rate, cost_of_capital, defaults_warnings = _defaults(session)

    file_warnings = list(file_warnings) + list(defaults_warnings)
    results = _check_rows(parsed_rows, records, existing)
    summary = _summary(results, fmt, file_warnings)

    if mode == "preview":
        token, expires_at = imports.sign_token(raw, production=deps.is_production())
        return ImportPreviewResponse(
            as_of=as_of,
            filename=file.filename or "invoice_history.csv",
            import_token=token,
            expires_at=expires_at,
            rows=results,
            summary=summary,
            note=IMPORT_NOTE,
        )

    # ------------------------------------------------------------- commit ----
    token = (import_token or x_import_token or "").strip()
    created_case_ids: list[str] = []
    payment_ids: list[str] = []
    skipped: list[str] = []
    seen_keys = dict(existing)

    for index, row in enumerate(parsed_rows):
        result = results[index]
        if result.status == "INVALID":
            summary.failed_rows += 1
            continue
        if result.status == "DUPLICATE":
            summary.skipped_rows += 1
            skipped.append(f"row {row.row_no}: {row.invoice_no} is already in your book")
            continue

        calculation_date = as_of
        payload = imports.case_request_payload(
            row,
            case_id=new_ulid(),
            calculation_date=calculation_date,
            supplier=supplier,
            tax_rate_pct=tax_rate,
            cost_of_capital_pct=cost_of_capital,
        )
        try:
            detail = case_routes.create_case(
                CaseCreateRequest.model_validate(payload),
                Response(),
                None,
            )
        except HTTPException as exc:
            result.status = "FAILED"
            result.errors.append(str(exc.detail))
            summary.failed_rows += 1
            continue

        case_id = detail.case.id
        result.case_id = case_id
        result.status = "CREATED"
        created_case_ids.append(case_id)
        summary.created_rows += 1
        if row.invoice_no and row.buyer_name:
            seen_keys[_buyer_key(row.buyer_gstin, row.buyer_name, row.invoice_no)] = case_id

        if row.has_payment and row.paid_on is not None and row.paid_amount is not None:
            try:
                case_routes.create_case_payment(
                    case_id,
                    PaymentCreateRequest(
                        amount=row.paid_amount,
                        paid_on=row.paid_on,
                        method=PaymentMethod.OTHER,
                        note=PAYMENT_NOTE,
                    ),
                    idempotency_key=f"import:{token.split('.')[0]}:{row.row_no}",
                )
            except HTTPException as exc:
                result.warnings.append(
                    f"The invoice was created, but the payment was not recorded: {exc.detail}"
                )
            else:
                summary.payments_created += 1
                with session_scope() as session:
                    payments = customer_book.payments_for_case(
                        session, case_id, include_voided=True
                    )
                    if payments:
                        result.payment_id = payments[-1].id
                        payment_ids.append(payments[-1].id)

    return ImportCommitResponse(
        as_of=as_of,
        filename=file.filename or "invoice_history.csv",
        import_token=token,
        rows=results,
        summary=summary,
        created_case_ids=created_case_ids,
        payment_ids=payment_ids,
        skipped=skipped,
        note=IMPORT_NOTE,
    )


__all__ = ["router", "IMPORT_NOTE", "PAYMENT_NOTE"]
