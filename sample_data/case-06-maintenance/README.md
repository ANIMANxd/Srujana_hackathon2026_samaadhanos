# Case 06 - Sample Maintenance Services

A service invoice with **no delivery date and no delivery proof**. This is the
case that shows the system refusing to invent an anchor.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0401.pdf` | the order | `PO` |
| `02-tax-invoice/INV-2026-0401.pdf` | the payable, 2,50,000.00 | `INVOICE` |
| `03-whatsapp/chat_no_delivery_confirmation.txt` | a promise, but no delivery line | `WHATSAPP` |

The chat's technician line ("completed the service check") is deliberately not
a delivery confirmation. The extractor must raise `DELIVERY_ANCHOR_MISSING`.

This case matches `contracts/fixtures/case_06.request.json` on dates and amount.
