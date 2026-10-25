# Case 01 - Sample Supplies Pvt Ltd

The golden-path demo. An overdue invoice, a 90-day term that cannot move the
statutory clock, delivery proof, and a WhatsApp promise to pay.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0114.pdf` | the order and the written Net-90 term | `PO` |
| `02-tax-invoice/INV-2026-0042.pdf` | the payable, 12,50,000.00 | `INVOICE` |
| `03-delivery/DC-2026-0088.pdf` | dispatched and received on 16/02/2026 | `DELIVERY_PROOF` |
| `03-delivery/GRN-2026-0088.pdf` | the buyer's own receipt, no rejection | `DELIVERY_PROOF` |
| `04-whatsapp/chat_delivery_and_promise.txt` | delivery plus a promise on 10/04/2026 | `WHATSAPP` |
| `../supplier-records/01-udyam/` | the enterprise's declared particulars | `UDYAM` |

Every `.pdf` has a `.txt` twin generated from the same content. The Udyam page
is a data extract, not a certificate, by design.

This case matches `contracts/fixtures/case_01.request.json` on dates and amount.
The supplier GSTIN is a distinct placeholder because the preset's buyers reuse
neighbouring numbers.
