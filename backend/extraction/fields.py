"""Label-anchored field extraction from plain-text invoices and POs.

Regex only, line by line, so every candidate carries the **line it was read
on** and the source line itself. Labels are what anchor each rule: a bare date
or a bare number in a text is never taken as a field, because in an export the
same shapes are chat timestamps. The one exception is the loose invoice-number
rule, which still requires a digit-bearing token after the word "invoice".

Values come back as strings in contract form (dates `YYYY-MM-DD`, money as a
`Decimal` quantised to `0.01`, credit days as an integer string). No float ever
touches an amount.

Confidences are extraction heuristics - how specific the pattern is - not legal
values. Every hit stays `machine_suggested` until a person confirms it.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Sequence

# A source line, trimmed for the response's `source_text`.
MAX_SNIPPET = 200


@dataclass(frozen=True)
class FieldHit:
    """One extracted candidate: value, the line it came from, and a confidence."""

    key: str
    value: str
    line: int
    source_text: str
    confidence: float
    ambiguous_date_order: bool = False


def extract_fields(lines: Sequence[str]) -> dict[str, FieldHit]:
    """Every field this text yields, keyed by name. Absent keys are simply absent.

    The caller fills the gaps with `method: missing` so the response always
    carries all the keys the contract names.
    """
    supplier_gstin, buyer_gstin = _gstins(lines)
    hits: dict[str, FieldHit | None] = {
        "invoice_number": _invoice_number(lines),
        "invoice_date": _labelled_date(lines, DATE_LABELS_INVOICE, "invoice_date"),
        "amount": _amount(lines),
        "supplier_gstin": supplier_gstin,
        "buyer_gstin": buyer_gstin,
        "buyer_name": _name(lines, BUYER_NAME_LABELS),
        "supplier_name": _name(lines, SUPPLIER_NAME_LABELS),
        "delivery_date": _labelled_date(lines, DATE_LABELS_DELIVERY, "delivery_date"),
        "po_reference": _po_reference(lines),
        "written_credit_days": _credit_days(lines),
    }
    return {key: hit for key, hit in hits.items() if hit is not None}


def _snippet(line: str) -> str:
    text = " ".join(line.split())
    return text if len(text) <= MAX_SNIPPET else text[: MAX_SNIPPET - 3] + "..."


def _find(
    lines: Sequence[str], pattern: re.Pattern[str]
) -> tuple[int, str, re.Match[str]] | None:
    """First line matching `pattern`: (1-based line, line text, match)."""
    for index, line in enumerate(lines, start=1):
        match = pattern.search(line)
        if match:
            return index, line, match
    return None


# ------------------------------------------------------------ invoice no ----

_INVOICE_LABELLED = re.compile(
    r"\binvoice\s*(?:no\.?|number|#)\s*[:\-]?\s*(?P<v>[A-Za-z0-9][A-Za-z0-9/-]{2,19})\b",
    re.IGNORECASE,
)
# Loose form: "against invoice SYN-INV-0042". The token must carry a digit, so
# "invoice dated" or "invoice will" can never be read as a number.
_INVOICE_LOOSE = re.compile(
    r"\binvoice\s+(?P<v>[A-Za-z0-9][A-Za-z0-9/-]*\d[A-Za-z0-9/-]*)\b",
    re.IGNORECASE,
)
_NOT_AN_INVOICE_NUMBER = {
    "date",
    "dated",
    "number",
    "no",
    "copy",
    "value",
    "total",
    "due",
    "paid",
    "payment",
    "will",
    "the",
    "this",
    "that",
    "was",
    "is",
    "for",
    "of",
    "on",
    "in",
    "at",
    "by",
    "to",
    "we",
    "you",
    "our",
    "your",
    "and",
    "or",
    "not",
}


def _invoice_number(lines: Sequence[str]) -> FieldHit | None:
    for pattern, confidence in ((_INVOICE_LABELLED, 0.94), (_INVOICE_LOOSE, 0.85)):
        found = _find(lines, pattern)
        if not found:
            continue
        index, line, match = found
        value = match.group("v").strip("/-")
        if value.lower() in _NOT_AN_INVOICE_NUMBER or not value:
            continue
        return FieldHit("invoice_number", value, index, _snippet(line), confidence)
    return None


# ---------------------------------------------------------------- dates ----

# Labels that name the invoice date, and labels that name delivery. A date
# under any other label (due, payment, order, LR...) belongs to neither key.
# The empty entry "" is the empty label: a line that is just `: 12/01/2026`,
# which only the invoice key may claim.
DATE_LABELS_INVOICE: frozenset[str] = frozenset(
    {"", "date", "invoice", "dated", "bill"}
)
DATE_LABELS_DELIVERY: frozenset[str] = frozenset(
    {"delivery", "delivery date", "delivered", "lr", "challan", "expected delivery"}
)

# `Label: 12/01/2026`, `Label date: 12/01/2026`, or a bare `Date: ...`. The
# label may sit directly against the colon (`Delivery: 04/03/2026`), and the
# value must still look like a date - that is what keeps every other
# `Label: value` line out.
_LABELLED_DATE = re.compile(
    r"(?:(?P<label>[A-Za-z][A-Za-z ]{0,24}?)\s*)?(?:(?:dates?|dated)\b)?\s*[:\-]\s*"
    r"(?P<v>\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
    re.IGNORECASE,
)


def _labelled_date(
    lines: Sequence[str], allowed: frozenset[str], key: str
) -> FieldHit | None:
    """First date under a label this key owns.

    A bare `Date:` is only the *invoice* date - under the delivery key it would
    wrongly grab the invoice's own date - so the empty label lives only in the
    invoice key's set.
    """
    confidence = 0.95 if key == "invoice_date" else 0.9
    for index, line in enumerate(lines, start=1):
        for match in _LABELLED_DATE.finditer(line):
            label = (match.group("label") or "").strip().lower()
            accepted = label in allowed or any(
                label.startswith(a + " ") for a in allowed if a
            )
            if not accepted:
                continue
            parsed, ambiguous = _norm_date(match.group("v"))
            if parsed is None:
                continue
            hit_confidence = (
                confidence if not ambiguous else round(confidence - 0.05, 2)
            )
            return FieldHit(
                key, parsed, index, _snippet(line), hit_confidence, ambiguous
            )
    return None


def _norm_date(value: str) -> tuple[str | None, bool]:
    """Read a date string to ISO. Returns (iso, order_was_ambiguous).

    Indian exports are DD/MM/YYYY; a 2-digit year is 20xx. When both the day
    and the month are 12 or less the order genuinely cannot be told from the
    text, so the caller is told and the response carries a note.
    """
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value).isoformat(), False
        except ValueError:
            return None, False
    parts = re.split(r"[/.-]", value)
    if len(parts) != 3:
        return None, False
    if len(parts[0]) == 4:  # ISO order with / or . separators: 2026/01/12
        year_text, month_text, day_text = parts
    else:  # Indian exports: DD/MM/YYYY
        day_text, month_text, year_text = parts
    if not (day_text.isdigit() and month_text.isdigit() and year_text.isdigit()):
        return None, False
    year = int(year_text)
    if year < 100:
        year += 2000
    day, month = int(day_text), int(month_text)
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None, False
    ambiguous = day <= 12 and month <= 12 and day != month
    return parsed.isoformat(), ambiguous


# ---------------------------------------------------------------- amount ----

# Ordered by how specifically the label names the payable total, so "Grand
# Total" always beats an earlier "Total".
_AMOUNT_LABELS: tuple[tuple[str, float], ...] = (
    ("grand total", 0.93),
    ("total payable", 0.93),
    ("net payable", 0.93),
    ("amount payable", 0.92),
    ("invoice value", 0.9),
    ("total due", 0.9),
    ("balance due", 0.88),
    ("total amount", 0.88),
    ("total", 0.85),
)
_LABELLED_AMOUNT = {
    label: re.compile(
        rf"\b{re.escape(label)}\b\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*"
        r"(?P<v>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )
    for label, _ in _AMOUNT_LABELS
}

# A bare "Total" is the weakest label, so its line has to look like a payable
# total: tax rows, sub-totals and quantity lines all say "total" too.
_TOTAL_LINE_NOISE = re.compile(
    r"\b(cgst|sgst|igst|cess|tax|sub[\s-]?total|quantity|qty|discount|rate)\b",
    re.IGNORECASE,
)


def _amount(lines: Sequence[str]) -> FieldHit | None:
    for label, confidence in _AMOUNT_LABELS:
        pattern = _LABELLED_AMOUNT[label]
        for index, line in enumerate(lines, start=1):
            if label == "total" and _TOTAL_LINE_NOISE.search(line):
                continue
            match = pattern.search(line)
            if not match:
                continue
            rupees = _rupees(match.group("v"))
            if rupees is None:
                continue
            return FieldHit("amount", rupees, index, _snippet(line), confidence)
    return None


def _rupees(value: str) -> str | None:
    """`3,00,000.00` -> `300000.00`. Decimal in, Decimal out, no floats."""
    cleaned = value.replace(",", "").strip()
    if not cleaned or cleaned == "0" or set(cleaned) <= {"0"}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- GSTIN ----

_GSTIN = re.compile(r"\b\d{2}[A-Z]{3,10}\d{4,14}[A-Z0-9]{1,3}\d\b")
_BUYER_MARKERS = ("bill to", "buyer", "customer", "sold to", "ship to", "consignee")
_SUPPLIER_MARKERS = (
    "sold by",
    "seller",
    "supplier",
    "bill from",
    "from",
    "consignor",
    "our gstin",
)


def _gstins(lines: Sequence[str]) -> tuple[FieldHit | None, FieldHit | None]:
    """Read GSTINs and decide who is who from the line's own label.

    With no label at all the first GSTIN is read as the seller's (invoices
    header themselves) at a lower confidence, and the second as the buyer's -
    both flagged machine-suggested so the owner checks them.
    """
    found: list[tuple[str, int, str, str | None]] = []
    for index, line in enumerate(lines, start=1):
        lowered = line.lower()
        for match in _GSTIN.finditer(line):
            if any(marker in lowered for marker in _BUYER_MARKERS):
                role = "buyer"
            elif any(marker in lowered for marker in _SUPPLIER_MARKERS):
                role = "supplier"
            else:
                role = None
            found.append((match.group(0), index, _snippet(line), role))

    def hit(
        key: str, candidate: tuple[str, int, str, str | None], confidence: float
    ) -> FieldHit:
        value, index, snippet, _ = candidate
        return FieldHit(key, value, index, snippet, confidence)

    supplier = next((c for c in found if c[3] == "supplier"), None)
    buyer = next((c for c in found if c[3] == "buyer"), None)
    unassigned = [
        c for c in found if c[3] is None and c is not supplier and c is not buyer
    ]

    if supplier is None and unassigned:
        supplier = unassigned.pop(0)
    if buyer is None and unassigned:
        buyer = unassigned.pop(0)

    supplier_hit = (
        hit("supplier_gstin", supplier, 0.96 if supplier and supplier[3] else 0.72)
        if supplier
        else None
    )
    buyer_hit = (
        hit("buyer_gstin", buyer, 0.96 if buyer and buyer[3] else 0.72)
        if buyer
        else None
    )
    return supplier_hit, buyer_hit


# ----------------------------------------------------------------- names ----

BUYER_NAME_LABELS: tuple[str, ...] = (
    "bill to",
    "buyer",
    "customer",
    "sold to",
    "consignee",
)
SUPPLIER_NAME_LABELS: tuple[str, ...] = (
    "seller",
    "sold by",
    "supplier",
    "bill from",
    "from",
    "consignor",
)


def _name(lines: Sequence[str], labels: Sequence[str]) -> FieldHit | None:
    """`<label>: <name>` where the label is one this key owns.

    The value stops at a GSTIN mention so `Bill to: X, GSTIN 29...` yields the
    name alone (the GSTIN has its own key).
    """
    for label in labels:
        pattern = re.compile(
            rf"^\s*{re.escape(label)}\s*[:\-]\s*(?P<v>.+)$",
            re.IGNORECASE,
        )
        found = _find(lines, pattern)
        if not found:
            continue
        index, line, match = found
        value = re.split(r"\s+GSTIN\b", match.group("v"), maxsplit=1)[0].strip(" ,;(-")
        if not value:
            continue
        return FieldHit(
            "supplier_name" if label in SUPPLIER_NAME_LABELS else "buyer_name",
            value,
            index,
            _snippet(line),
            0.88,
        )
    return None


# ------------------------------------------------------------ PO / terms ----

_PO_LABELLED = re.compile(
    r"\b(?:your\s+)?(?:purchase\s+order|po)\b\s*"
    r"(?:no\.?|number|#|ref(?:erence)?|id)?\s*[:\-#]?\s*"
    r"(?P<v>[A-Za-z0-9][A-Za-z0-9/-]{2,31})\b",
    re.IGNORECASE,
)
_ORDER_LABELLED = re.compile(
    r"\b(?:your\s+)?order\b\s*(?:no\.?|number|#)?\s*[:\-#]?\s*"
    r"(?P<v>[A-Za-z0-9][A-Za-z0-9/-]{2,31})\b",
    re.IGNORECASE,
)


def _looks_like_reference(value: str) -> bool:
    """A PO number carries a digit, a hyphen, or shouted capitals - 'possible' does not."""
    if _norm_date(value)[0] or value.lower() in _NOT_AN_INVOICE_NUMBER:
        return False
    return bool(
        re.search(r"\d", value) or "-" in value or (value.isupper() and len(value) >= 4)
    )


def _po_reference(lines: Sequence[str]) -> FieldHit | None:
    for pattern, confidence in ((_PO_LABELLED, 0.9), (_ORDER_LABELLED, 0.88)):
        for index, line in enumerate(lines, start=1):
            for match in pattern.finditer(line):
                value = match.group("v").strip("/-#")
                if len(value) < 3 or not _looks_like_reference(value):
                    continue
                return FieldHit(
                    "po_reference", value, index, _snippet(line), confidence
                )
    return None


_CREDIT_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"\bnet\s+(?P<v>\d{1,3})\s*days?\b", re.IGNORECASE), 0.9),
    (
        re.compile(
            r"\b(?P<v>\d{1,3})\s*[-\s]day\s+(?:credit|terms|payment)\b", re.IGNORECASE
        ),
        0.87,
    ),
    (
        re.compile(
            r"\b(?P<v>\d{1,3})\s*days?\s+(?:credit|credit period|payment terms)\b",
            re.IGNORECASE,
        ),
        0.87,
    ),
    (
        re.compile(
            r"\bcredit\s+(?:period\s+)?(?:of\s+|:\s*)(?P<v>\d{1,3})\s*days?\b",
            re.IGNORECASE,
        ),
        0.87,
    ),
    (
        re.compile(
            r"\b(?:due|payment|payable)\s+(?:within|in)\s+(?P<v>\d{1,3})\s*days\b",
            re.IGNORECASE,
        ),
        0.88,
    ),
)


def _credit_days(lines: Sequence[str]) -> FieldHit | None:
    """Credit-day phrases (`Net 45 days`, `due within 30 days`) -> `transaction.written_credit_days`.

    Reported only when a document says it: a missing value keeps the request
    field null, which is what "no written agreement" means downstream (OQ-5).
    """
    for pattern, confidence in _CREDIT_PATTERNS:
        found = _find(lines, pattern)
        if not found:
            continue
        index, line, match = found
        days = int(match.group("v"))
        if days <= 0:
            continue
        return FieldHit(
            "written_credit_days", str(days), index, _snippet(line), confidence
        )
    return None
