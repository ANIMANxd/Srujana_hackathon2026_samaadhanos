"""What extraction can detect: source kinds, message tags, field keys.

Lives beside the pipeline (not in `schemas.py`) so the contract and the
extractors read one list of names, exactly like `backend.artifacts.kinds`.

The five message tags are the candidating vocabulary for the objection record:
they name what a chat line *reads like*, not what the law makes of it. Whether
an objection qualifies is the engine's decision, made later from the confirmed
request.
"""

from enum import Enum


class SourceKind(str, Enum):
    """Which kind of upload the text looked like (detected, not declared)."""

    WHATSAPP_EXPORT = "WHATSAPP_EXPORT"
    DOCUMENT_TEXT = "DOCUMENT_TEXT"


class MessageTag(str, Enum):
    DELIVERY_CONFIRMATION = "DELIVERY_CONFIRMATION"
    DEFECT_OBJECTION = "DEFECT_OBJECTION"
    RESOLUTION_ACK = "RESOLUTION_ACK"
    LATE_COMPLAINT = "LATE_COMPLAINT"
    PAYMENT_PROMISE = "PAYMENT_PROMISE"


class ExtractionMethod(str, Enum):
    """How a value was read. `missing` means no value, not a failed parse."""

    REGEX = "regex"
    LLM = "llm"
    MISSING = "missing"


# Keys of `ExtractionResponse.fields`. The first eight are the keys the
# frontend already mirrors (CR-4); `written_credit_days` carries the credit-day
# phrases task B9 asks for. `supplier_name` is a top-level string in the
# response, not a field entry, because CR-4 reads it that way.
FIELD_KEYS: tuple[str, ...] = (
    "invoice_number",
    "invoice_date",
    "amount",
    "supplier_gstin",
    "buyer_gstin",
    "buyer_name",
    "delivery_date",
    "po_reference",
    "written_credit_days",
)
