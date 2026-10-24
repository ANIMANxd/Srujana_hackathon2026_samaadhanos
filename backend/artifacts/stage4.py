"""Stage 4: the evidence pack - portal checklist, chronology, interest sheet, certificate.

Four parts, in the order the pack reads (architecture.md section 7: "a
portal-fields checklist plus evidence bundle, **not** a fabricated official
form"):

1. Portal fields - the V10 capture's field list, or the honest fallback telling
   the owner to confirm every field against the live portal.
2. Evidence in date order - one chronological ledger of the case's dated events
   plus the documents held, so nothing is asserted that the inputs do not hold.
3. Interest calculation sheet - the engine's rate segments, ledger rows and
   totals, printed as computed.
4. A certificate template (BSA s.63), clearly marked as a template to be
   completed and signed by the person responsible - never an issued certificate.

Everything printed here comes from `request` inputs or the engine's response;
the pack computes nothing, and no portal field name is invented.
"""

from datetime import date as date_type

from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.artifacts.common import (
    EVIDENCE_LABELS,
    assumptions_section,
    bullets,
    closing_footer,
    draft_banner,
    inr,
    join_blocks,
    md_table,
    open_points_section,
    pct,
)
from backend.artifacts.portal_fields import portal_checklist
from backend.engine.text import contract_str

UNKNOWN = "\u2014"

ACK_LABELS = {
    "SIGNED_BALANCE_CONFIRMATION": "Signed balance confirmation",
    "PART_PAYMENT": "Part-payment",
    "WHATSAPP_PROMISE": "WhatsApp promise",
}


def evidence_pack(
    request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse
) -> str:
    """Build the Stage 4 pack from an evaluation that carries a ledger."""
    assert (
        evaluation.financials is not None
    ), "availability() only offers this draft when the ledger was computed"
    financials = evaluation.financials
    calc = evaluation.calculation_date.isoformat()

    portal_note, portal_rows = portal_checklist()
    portal = "\n".join(
        [
            "## Portal fields",
            "",
            portal_note,
            "",
            *portal_rows,
        ]
    )

    chronology = "\n".join(
        [
            "## Evidence in date order",
            "",
            md_table(
                ["Date", "Event", "Where it comes from"],
                _chronology(request, evaluation),
            ),
            "",
            "### Documents in this case",
            "",
            md_table(["Document", "Reference", "Status"], _documents(request)),
        ]
    )

    interest = "\n".join(
        [
            "## Interest calculation sheet",
            "",
            "### How the calculation was run",
            "",
            bullets(
                [
                    f"Rate mode: {contract_str(financials.rate_mode)}",
                    f"Appropriation of payments: {contract_str(financials.appropriation_mode)}",
                    f"Part-payments: {contract_str(financials.payment_boundary_convention)}",
                    f"Every figure below is as on {calc}.",
                ]
            ),
            "",
            "### Rate segments",
            "",
            md_table(
                ["From", "To", "Bank Rate", "Rate applied"],
                [
                    [
                        s.from_.isoformat(),
                        s.to.isoformat(),
                        pct(s.bank_rate_pct),
                        pct(s.statutory_rate_pct),
                    ]
                    for s in financials.rate_segments
                ],
            ),
            "",
            "### Ledger",
            "",
            md_table(
                [
                    "Row",
                    "From",
                    "To",
                    "Opening",
                    "Interest",
                    "Payment",
                    "Closing",
                    "Rate",
                    "Note",
                ],
                [
                    [
                        contract_str(row.kind),
                        row.from_.isoformat(),
                        row.to.isoformat(),
                        inr(row.opening),
                        inr(row.interest),
                        inr(row.payment),
                        inr(row.closing),
                        pct(row.rate_pct),
                        row.note or "",
                    ]
                    for row in financials.ledger
                ],
            ),
            "",
            "### Totals",
            "",
            md_table(
                ["Total", "Amount"],
                [
                    [
                        "Interest accrued across the rows",
                        inr(financials.interest_total),
                    ],
                    ["Principal outstanding", inr(financials.principal_outstanding)],
                    [
                        "Interest still outstanding",
                        inr(financials.interest_outstanding),
                    ],
                    ["Total claim", inr(financials.total_claim)],
                    ["Movement on this balance per day", inr(financials.daily_accrual)],
                ],
            ),
            "",
            "Each ledger row is rounded to 0.01 (half-up) by the engine as it computes "
            "it; the totals above are the engine's own totals.",
        ]
    )

    certificate = "\n".join(
        [
            "## Certificate for electronic records (BSA s.63) \u2014 TEMPLATE",
            "",
            "**TEMPLATE.** To be completed and signed by the person responsible for the "
            "computer or device that holds these records. This is a blank template, not "
            "an issued certificate, and nothing has been signed. Check the wording "
            "against the primary source before use: that capture is not in this repo's "
            "statute sheet yet.",
            "",
            "I, [full name], [role] of "
            + request.supplier.name
            + ", state that the electronic records listed in this pack were produced "
            "from [device / system] in the ordinary course of business, and that the "
            "device was operating properly at the relevant time.",
            "",
            "Records covered by this certificate: [list or annexure reference]",
            "",
            "Name and designation: ______________________________",
            "",
            "Signature: ______________________________    Date: ______________________________",
        ]
    )

    artifact_assumptions = [
        (
            "Every date, amount and rate in this pack comes from your case inputs and "
            f"this case's calculation as on {calc}; nothing is worked out here."
        ),
        (
            "The portal section names no field until the V10 capture exists, so each row "
            "asks for confirmation against the live portal instead."
        ),
        (
            "The certificate section is a blank template to complete and sign; its "
            "wording still has to be checked against the primary source."
        ),
        (
            "Documents the case does not hold are listed as missing rather than left "
            "out, so the pack shows the gaps as well as the evidence."
        ),
    ]

    banner = draft_banner(
        case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
    )
    banner += (
        "\n> Prepared as a checklist and evidence bundle. Not a government form, and no "
        "portal field is asserted before V10 is captured."
    )

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: evidence pack (Stage 4)",
        banner,
        portal,
        chronology,
        interest,
        certificate,
        assumptions_section([*artifact_assumptions, *evaluation.assumptions]),
        open_points_section(evaluation.warnings),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )


def _chronology(
    request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse
) -> list[list[str]]:
    """Every dated event of the case, oldest first.

    Sorting is by date only - a stable sort keeps same-day events in the order
    the case lists them, so the table never reorders facts to suit itself.
    """
    txn = request.transaction
    timeline = evaluation.timeline
    evidence_ref = {
        item.kind.value: item.ref for item in request.evidence.items if item.ref
    }
    rows: list[tuple[date_type, str, str]] = []

    def add(day: date_type | None, event: str, where: str = "") -> None:
        if day is not None:
            rows.append((day, event, where))

    add(txn.contract_date, "PO / agreement date", evidence_ref.get("PO", ""))
    add(txn.supply_date, "Supply date")
    add(txn.invoice_date, "Invoice issued", evidence_ref.get("INVOICE", ""))
    add(
        timeline.delivery_date if timeline else None,
        "Delivered",
        evidence_ref.get("DELIVERY_PROOF", ""),
    )
    for objection in request.objections:
        add(
            objection.raised_date,
            "Objection raised" + ("" if objection.is_written else " (not in writing)"),
            objection.description or "",
        )
        add(objection.resolved_date, "Objection resolved")
    for complaint in timeline.late_complaints if timeline else []:
        add(complaint.date, "Complaint recorded, outside the window", complaint.reason)
    add(
        timeline.objection_window_end if timeline else None,
        "Last day to raise a written objection",
        "from this case's calculation",
    )
    add(
        timeline.acceptance_date if timeline else None,
        "Acceptance date used by the calculation",
        f"status: {contract_str(timeline.objection_status)}" if timeline else "",
    )
    add(
        timeline.due_date if timeline else None,
        "Payment due",
        "from this case's calculation",
    )
    add(
        timeline.appointed_day if timeline else None,
        "Appointed day (the due date plus one)",
        "from this case's calculation",
    )
    for payment in request.part_payments:
        note = inr(payment.amount) + (
            f" \u00b7 {payment.reference}" if payment.reference else ""
        )
        add(payment.date, "Part-payment received", note)
    for ack in request.acknowledgments:
        label = ACK_LABELS.get(
            contract_str(ack.kind), contract_str(ack.kind).replace("_", " ").title()
        )
        note = "signed" if ack.is_signed else "not signed"
        if ack.source_ref:
            note += f" \u00b7 {ack.source_ref}"
        add(ack.date, label, note)
    add(
        evaluation.calculation_date,
        "Calculation date for this pack",
        "all figures are as on this date",
    )

    rows.sort(key=lambda row: row[0])
    return [[day.isoformat(), event, where or UNKNOWN] for day, event, where in rows]


def _documents(request: CaseEvaluationRequest) -> list[list[str]]:
    """The evidence the request reports, including what is not held (gaps show)."""
    rows = []
    for item in request.evidence.items:
        label = EVIDENCE_LABELS.get(item.kind.value, item.kind.value)
        rows.append(
            [label, item.ref or UNKNOWN, "held" if item.present else "not in this case"]
        )
    return rows
