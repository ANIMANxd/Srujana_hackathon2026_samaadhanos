"""The confirm schema: where each candidate would go in a CaseEvaluationRequest.

This is the map the confirmation screen is built from. It carries **no values**
- values live in `fields` and `messages` - only the target path, the type, and
a note saying what a human should check before ticking.

Paths are real contract paths, and `backend/tests/contract/test_extraction.py`
resolves every one of them against the Pydantic models, so a rename in the
contract fails the build instead of silently pointing at nothing.

`path: null` means the request genuinely has nowhere to put the value; the note
says where to keep it instead of inventing a field.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmSpec:
    key: str
    path: str | None
    kind: str  # "field" for an extracted value, "message" for a chat tag
    type: str  # "date" | "money" | "int" | "string" | "row"
    required: bool
    note: str


CONFIRM_SCHEMA: tuple[ConfirmSpec, ...] = (
    # ---------------------------------------------------- document fields ----
    ConfirmSpec(
        key="supplier_name",
        path="supplier.name",
        kind="field",
        type="string",
        required=True,
        note="Machine-suggested from the document header; check it against the "
        "Udyam certificate before it becomes the request's supplier name.",
    ),
    ConfirmSpec(
        key="invoice_number",
        path="evidence.items[INVOICE].ref",
        kind="field",
        type="string",
        required=False,
        note="The request has no invoice-number field of its own; the invoice "
        "reference sits on the INVOICE evidence item, or stays in your records.",
    ),
    ConfirmSpec(
        key="invoice_date",
        path="transaction.invoice_date",
        kind="field",
        type="date",
        required=True,
        note="Required by the request. The engine anchors nothing on it - delivery "
        "does that - but it must be the date on the document.",
    ),
    ConfirmSpec(
        key="amount",
        path="transaction.principal",
        kind="field",
        type="money",
        required=True,
        note="The value of the supply. Everything the engine computes runs from "
        "this figure, so confirm it against the invoice total line.",
    ),
    ConfirmSpec(
        key="supplier_gstin",
        path=None,
        kind="field",
        type="string",
        required=False,
        note="The request has no supplier GSTIN field. Keep it in your records or "
        "on the GST_RETURN evidence reference; there is nothing to map it to.",
    ),
    ConfirmSpec(
        key="buyer_gstin",
        path="buyer.gstin",
        kind="field",
        type="string",
        required=False,
        note="Buyer GSTIN as printed on the invoice; used only to identify the buyer.",
    ),
    ConfirmSpec(
        key="buyer_name",
        path="buyer.name",
        kind="field",
        type="string",
        required=True,
        note="Exactly the name on the invoice's bill-to line, spelling included.",
    ),
    ConfirmSpec(
        key="delivery_date",
        path="transaction.delivery_date",
        kind="field",
        type="date",
        required=False,
        note="Leave null only if there is genuinely no delivery proof: a missing "
        "delivery date blocks Stage 4 and leaves acceptance unresolved (6.2).",
    ),
    ConfirmSpec(
        key="po_reference",
        path="evidence.items[PO].ref",
        kind="field",
        type="string",
        required=False,
        note="The PO number as printed. The request records it as the PO evidence "
        "item's reference rather than as a date or an amount.",
    ),
    ConfirmSpec(
        key="written_credit_days",
        path="transaction.written_credit_days",
        kind="field",
        type="int",
        required=False,
        note="Only what a written document actually says. Null means no written "
        "agreement was supplied; what counts as one is still open (OQ-5).",
    ),
    # ------------------------------------------------------- chat messages ----
    ConfirmSpec(
        key="DELIVERY_CONFIRMATION",
        path="transaction.delivery_date",
        kind="message",
        type="date",
        required=False,
        note="Use the message's date as delivery_date, and point the DELIVERY_PROOF "
        "evidence item's reference at this line of the chat export.",
    ),
    ConfirmSpec(
        key="DEFECT_OBJECTION",
        path="objections[]",
        kind="message",
        type="row",
        required=False,
        note="Add an objections[] row: raised_date = the message date, is_written = "
        "true (a chat is writing), description = the message text. The engine, not "
        "this screen, decides whether it qualifies.",
    ),
    ConfirmSpec(
        key="LATE_COMPLAINT",
        path="objections[]",
        kind="message",
        type="row",
        required=False,
        note="Same row shape as a DEFECT_OBJECTION, but the date falls after the "
        "configured objection window, so the engine will record it as a complaint "
        "that does not move the clock rather than as a qualifying objection (6.2).",
    ),
    ConfirmSpec(
        key="RESOLUTION_ACK",
        path="objections[].resolved_date",
        kind="message",
        type="date",
        required=False,
        note="The message date becomes resolved_date on the objection it answers, "
        "which is what closes that objection for the engine.",
    ),
    ConfirmSpec(
        key="PAYMENT_PROMISE",
        path="acknowledgments[]",
        kind="message",
        type="row",
        required=False,
        note="Add an acknowledgments[] row: kind = WHATSAPP_PROMISE, is_signed = "
        "false, date = the message date. The engine records it as a promise that "
        "does not restart the limitation clock (6.5).",
    ),
)
