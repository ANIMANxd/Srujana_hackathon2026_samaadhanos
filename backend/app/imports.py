"""CSV invoice import: parsing, file-level rules and the preview token.

Pure parsing, no DB and no network: the caller supplies the bytes and the
calculation date. The route module (`app/routes/imports.py`) does the database
work and runs the frozen engine through the same path as `POST /cases`.

Rules this module owns:

- **One file, one date format.** `YYYY-MM-DD` or `DD-MM-YYYY` is detected across
  the whole file; a file that mixes them is refused rather than guessed at.
- **Indian money.** `1,25,000.00` and `125000.00` both parse to `Decimal`; floats
  are never used.
- **CSV injection guard.** A cell that starts with `=`, `+`, `-` or `@` is
  refused, because the same rows are exported again later. The row is reported,
  never silently cleaned.
- **Nothing is invented.** The supplier block, the buyer tax rate and the cost of
  capital are not in the file; the caller passes the owner's existing defaults
  and the response warns that they were used.
- **The preview token is stateless.** It signs the SHA-256 of the exact bytes
  with an expiry, so committing requires sending the same file back. No staging
  row and no temp file is written, which is what "preview stores nothing" means
  here.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2_000
TOKEN_TTL_SECONDS = 1_800
TOKEN_VERSION = "v1"

TWO_PLACES = Decimal("0.01")

REQUIRED_COLUMNS: tuple[str, ...] = (
    "invoice_no",
    "invoice_date",
    "delivery_date",
    "amount",
    "buyer_name",
)
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "buyer_gstin",
    "agreed_credit_days",
    "paid_on",
    "paid_amount",
    "notes",
)
ALL_COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
DATE_COLUMNS: tuple[str, ...] = ("invoice_date", "delivery_date", "paid_on")

# A cell beginning with any of these characters is a spreadsheet formula.
FORMULA_PREFIXES = ("=", "+", "-", "@")

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$", re.ASCII)
DMY_DATE = re.compile(r"^\d{2}-\d{2}-\d{4}$", re.ASCII)
INDIAN_AMOUNT = re.compile(r"^\d{1,2}(,\d{2})*,\d{3}(\.\d{1,2})?$", re.ASCII)
WESTERN_AMOUNT = re.compile(r"^\d{1,3}(,\d{3})+(\.\d{1,2})?$", re.ASCII)
PLAIN_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$", re.ASCII)

DATE_FORMAT_ISO = "YYYY-MM-DD"
DATE_FORMAT_DMY = "DD-MM-YYYY"

# A development-only signing key. Production must set IMPORT_TOKEN_SECRET, and
# the route refuses the fallback when APP_ENV=production (deps.is_production).
DEV_IMPORT_SECRET = "samadhaan-local-import-token-development-only"

SUPPLIER_WARNING = (
    "The file has no supplier details, buyer tax rate or cost of capital. The "
    "import used your most recent case's profile when one exists, otherwise a "
    "labelled placeholder. Check the new case before relying on eligibility or "
    "the buyer-cost lines."
)


class ImportFileError(Exception):
    """A file-level refusal: plain English, rendered as the API error envelope."""

    def __init__(self, code: str, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class ParsedInvoice:
    """One CSV row after parsing, with everything still wrong about it listed."""

    row_no: int
    values: dict[str, str] = field(default_factory=dict)
    invoice_no: str | None = None
    invoice_date: date | None = None
    delivery_date: date | None = None
    amount: Decimal | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    agreed_credit_days: int | None = None
    paid_on: date | None = None
    paid_amount: Decimal | None = None
    notes: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def has_payment(self) -> bool:
        return self.paid_on is not None and self.paid_amount is not None


# ------------------------------------------------------------------ token ----


def token_secret(*, production: bool = False) -> str:
    """`IMPORT_TOKEN_SECRET`, or the labelled development key.

    A production deployment without the variable is a configuration error: a
    token signed with a published key would let anyone commit a file that was
    never previewed.
    """
    value = os.environ.get("IMPORT_TOKEN_SECRET", "").strip()
    if value:
        return value
    if production:
        raise ImportFileError(
            "IMPORT_TOKEN_SECRET_MISSING",
            "The server has no IMPORT_TOKEN_SECRET, so previews cannot be signed. "
            "Set it before importing in production.",
            status=500,
        )
    return DEV_IMPORT_SECRET


def _signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def sign_token(
    raw: bytes, *, now: float | None = None, production: bool = False
) -> tuple[str, datetime]:
    """A token binding these exact bytes, with an expiry."""
    moment = time.time() if now is None else now
    expiry = int(moment) + TOKEN_TTL_SECONDS
    payload = f"{TOKEN_VERSION}:{expiry}:{hashlib.sha256(raw).hexdigest()}"
    token = f"{expiry}.{_signature(payload, token_secret(production=production))}"
    return token, datetime.fromtimestamp(expiry, UTC)


def verify_token(
    token: str | None, raw: bytes, *, now: float | None = None, production: bool = False
) -> str | None:
    """`None` when the token is valid for these bytes, else a plain-English reason."""
    if not token or not token.strip():
        return (
            "This step needs the import_token returned by the preview of this exact "
            "file. Preview first, then commit with the same file."
        )
    moment = time.time() if now is None else now
    parts = token.strip().split(".")
    if len(parts) != 2 or not parts[0].isdigit():
        return "The import_token is not in the form the preview returned."
    expiry = int(parts[0])
    if expiry < int(moment):
        return "This import_token has expired. Preview the file again."
    payload = f"{TOKEN_VERSION}:{expiry}:{hashlib.sha256(raw).hexdigest()}"
    expected = _signature(payload, token_secret(production=production))
    if not hmac.compare_digest(expected, parts[1]):
        return (
            "This import_token does not match the file you sent. Commit the same "
            "file you previewed, or preview again."
        )
    return None


# ---------------------------------------------------------------- parsing ----


def _clean_header(name: str | None) -> str:
    return (name or "").strip().lstrip("\ufeff").lower()


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError(
            "NOT_UTF8",
            "The file is not UTF-8 text. Save it as CSV UTF-8 and try again.",
        ) from exc


def _detect_date_format(texts: list[str]) -> str:
    """One format for the whole file, or a file-level refusal."""
    seen = set()
    for text in texts:
        value = text.strip()
        if not value:
            continue
        if ISO_DATE.fullmatch(value):
            seen.add(DATE_FORMAT_ISO)
        elif DMY_DATE.fullmatch(value):
            seen.add(DATE_FORMAT_DMY)
    if len(seen) > 1:
        raise ImportFileError(
            "MIXED_DATE_FORMATS",
            "This file mixes date formats (YYYY-MM-DD and DD-MM-YYYY). Use one "
            "format in every date cell and upload it again.",
        )
    return next(iter(seen)) if seen else DATE_FORMAT_ISO


def parse_amount(text: str, *, label: str) -> tuple[Decimal | None, str | None]:
    """A positive rupee amount, Indian or plain grouping, or a plain-English error."""
    value = text.strip().replace("\u20b9", "").replace(" ", "")
    if not value:
        return None, f"{label} is empty. Enter an amount such as 1,25,000.00."
    if value.startswith(FORMULA_PREFIXES):
        return None, (
            f"{label} starts with {value[0]!r}, which a spreadsheet reads as a "
            "formula. Amounts must be plain digits (CSV injection guard)."
        )
    if not (
        PLAIN_AMOUNT.fullmatch(value)
        or INDIAN_AMOUNT.fullmatch(value)
        or WESTERN_AMOUNT.fullmatch(value)
    ):
        return None, (
            f"{label} {text.strip()!r} is not a number I can read. Use digits with "
            "an optional decimal part, for example 1,25,000.00."
        )
    digits = value.replace(",", "")
    try:
        amount = Decimal(digits)
    except ArithmeticError:
        return None, f"{label} {text.strip()!r} is not a number I can read."
    if not amount.is_finite():
        return None, f"{label} must be a finite number."
    if amount <= 0:
        return None, f"{label} must be more than zero."
    rounded = amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if rounded != amount:
        return None, f"{label} can have at most two decimal places."
    return rounded, None


def parse_date(text: str, fmt: str, *, label: str) -> tuple[date | None, str | None]:
    value = text.strip()
    if not value:
        return None, f"{label} is empty. Enter a date as {fmt}."
    pattern = ISO_DATE if fmt == DATE_FORMAT_ISO else DMY_DATE
    if not pattern.fullmatch(value):
        return None, f"{label} {value!r} is not in this file's date format ({fmt})."
    try:
        if fmt == DATE_FORMAT_ISO:
            return date.fromisoformat(value), None
        day, month, year = value.split("-")
        return date(int(year), int(month), int(day)), None
    except ValueError:
        return None, f"{label} {value!r} is not a real calendar date."


def _formula_cell(column: str, text: str) -> str | None:
    value = text.strip()
    if value.startswith(FORMULA_PREFIXES):
        return (
            f"Column {column} starts with {value[0]!r}, which a spreadsheet reads as "
            "a formula. Remove the leading character (CSV injection guard)."
        )
    return None


def read_rows(raw: bytes) -> tuple[list[ParsedInvoice], str, list[str]]:
    """Parse every row. Returns rows, the file's date format, and file warnings."""
    if not raw:
        raise ImportFileError("EMPTY_FILE", "The file is empty.")
    if len(raw) > MAX_BYTES:
        raise ImportFileError(
            "FILE_TOO_LARGE",
            f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB. Split it into "
            "smaller files.",
            status=413,
        )
    text = _decode(raw)
    try:
        records = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise ImportFileError(
            "MALFORMED_CSV", f"The file could not be read as CSV: {exc}"
        ) from exc

    records = [record for record in records if any(cell.strip() for cell in record)]
    if not records:
        raise ImportFileError("EMPTY_FILE", "The file has no rows.")

    header = [_clean_header(cell) for cell in records[0]]
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        raise ImportFileError(
            "MISSING_COLUMNS",
            "The header is missing these required columns: "
            + ", ".join(missing)
            + ". Download the template and keep its header row.",
        )
    duplicates = {name for name in header if header.count(name) > 1}
    if duplicates:
        raise ImportFileError(
            "DUPLICATE_COLUMNS",
            "The header repeats these columns: " + ", ".join(sorted(duplicates)) + ".",
        )

    body = records[1:]
    if not body:
        raise ImportFileError("NO_DATA_ROWS", "The file has a header but no data rows.")
    if len(body) > MAX_ROWS:
        raise ImportFileError(
            "TOO_MANY_ROWS",
            f"The file has {len(body)} data rows; the limit is {MAX_ROWS} per import.",
        )

    dict_rows: list[dict[str, str]] = []
    for record in body:
        cells = {}
        for index, name in enumerate(header):
            cells[name] = record[index] if index < len(record) else ""
        dict_rows.append(cells)

    # One date format for the file, decided before any row is parsed.
    date_texts = [row.get(column, "") for row in dict_rows for column in DATE_COLUMNS]
    fmt = _detect_date_format(date_texts)

    rows: list[ParsedInvoice] = []
    for index, cells in enumerate(dict_rows, start=2):  # row 1 is the header
        row = ParsedInvoice(row_no=index, values=dict(cells))
        for column in ALL_COLUMNS:
            problem = _formula_cell(column, cells.get(column, ""))
            if problem:
                row.errors.append(problem)

        row.invoice_no = (cells.get("invoice_no") or "").strip() or None
        if not row.invoice_no:
            row.errors.append("invoice_no is required.")

        row.buyer_name = (cells.get("buyer_name") or "").strip() or None
        if not row.buyer_name:
            row.errors.append("buyer_name is required (the buyer must be named).")

        row.buyer_gstin = (cells.get("buyer_gstin") or "").strip() or None

        row.invoice_date, problem = parse_date(
            cells.get("invoice_date", ""), fmt, label="invoice_date"
        )
        if problem:
            row.errors.append(problem)
        row.delivery_date, problem = parse_date(
            cells.get("delivery_date", ""), fmt, label="delivery_date"
        )
        if problem:
            row.errors.append(problem)

        row.amount, problem = parse_amount(cells.get("amount", ""), label="amount")
        if problem:
            row.errors.append(problem)

        credit_text = (cells.get("agreed_credit_days") or "").strip()
        if credit_text:
            if not credit_text.isdigit():
                row.errors.append(
                    "agreed_credit_days must be a whole number of days, or blank."
                )
            else:
                row.agreed_credit_days = int(credit_text)

        paid_on_text = (cells.get("paid_on") or "").strip()
        paid_amount_text = (cells.get("paid_amount") or "").strip()
        if paid_on_text:
            row.paid_on, problem = parse_date(paid_on_text, fmt, label="paid_on")
            if problem:
                row.errors.append(problem)
        if paid_amount_text:
            row.paid_amount, problem = parse_amount(
                paid_amount_text, label="paid_amount"
            )
            if problem:
                row.errors.append(problem)
        if paid_on_text and not paid_amount_text:
            row.errors.append(
                "paid_on is set but paid_amount is empty; give both or neither."
            )
        if paid_amount_text and not paid_on_text:
            row.errors.append(
                "paid_amount is set but paid_on is empty; give both or neither."
            )

        row.notes = (cells.get("notes") or "").strip() or None

        if row.paid_on and row.invoice_date and row.paid_on < row.invoice_date:
            row.errors.append("paid_on cannot be before invoice_date.")
        if row.paid_amount and row.amount:
            if row.paid_amount > row.amount:
                row.errors.append(
                    "paid_amount is more than amount; a payment cannot exceed the "
                    "invoice."
                )
            elif row.paid_amount < row.amount:
                row.warnings.append(
                    "paid_amount is less than amount, so the invoice stays open with "
                    "the rest outstanding."
                )

        rows.append(row)
    return rows, fmt, []


# ------------------------------------------------------------- case input ----


DEFAULT_SUPPLIER: dict[str, object] = {
    # A labelled placeholder, not the owner's real profile: the CSV carries no
    # supplier block. `nic_codes` is non-empty only because the frozen gate's
    # `activity_match` check returns `passed=[]` (a list, not a bool) when a
    # non-trading activity is stated with no NIC codes; see CQ-52. Nothing here
    # is treated as a fact: every import row is warned to confirm it.
    "name": "Imported supplier (confirm your details)",
    "udyam_number": None,
    "enterprise_class": "SMALL",
    "activity": "MANUFACTURING",
    "nic_codes": ["25990"],
    "udyam_registration_date": None,
    "investment_cr": None,
    "turnover_cr": None,
}


def case_request_payload(
    row: ParsedInvoice,
    *,
    case_id: str,
    calculation_date: date,
    supplier: dict[str, object],
    tax_rate_pct: str,
    cost_of_capital_pct: str,
) -> dict[str, object]:
    """The `POST /cases` body for one row, so the import uses the same path.

    Only the file's own columns become facts. Contract date and acknowledgments
    stay empty; the invoice is the only evidence the import can honestly claim,
    because the file carries no documents.
    """
    assert row.invoice_no and row.invoice_date and row.delivery_date and row.amount
    assert row.buyer_name
    return {
        "contract_version": "1.0",
        "case_id": case_id,
        "supplier": dict(supplier),
        "buyer": {
            "name": row.buyer_name,
            "gstin": row.buyer_gstin,
            "tax_rate_pct": tax_rate_pct,
            "cost_of_capital_pct": cost_of_capital_pct,
        },
        "transaction": {
            "contract_date": None,
            "supply_date": row.delivery_date.isoformat(),
            "invoice_date": row.invoice_date.isoformat(),
            "delivery_date": row.delivery_date.isoformat(),
            "principal": format(row.amount, "f"),
            "written_credit_days": row.agreed_credit_days,
            "calculation_date": calculation_date.isoformat(),
            "years_deferred": None,
        },
        "objections": [],
        "part_payments": [],
        "acknowledgments": [],
        "evidence": {
            "items": [
                {"kind": "INVOICE", "present": True, "ref": row.invoice_no},
                {"kind": "PO", "present": False, "ref": None},
                {"kind": "DELIVERY_PROOF", "present": False, "ref": None},
                {"kind": "WHATSAPP", "present": False, "ref": None},
                {"kind": "UDYAM", "present": False, "ref": None},
                {"kind": "GST_RETURN", "present": False, "ref": None},
            ]
        },
        "config_overrides": None,
    }
