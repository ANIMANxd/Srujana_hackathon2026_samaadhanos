# Case 02 - Sample Micro Works

A micro enterprise, a 30-day term, and a written objection nine days after
delivery. The objection is inside the configured 15-day window; the replacement
arrives on day 18.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0209.pdf` | the order and the Net-30 term | `PO` |
| `02-tax-invoice/INV-2026-0209.pdf` | the payable, 3,00,000.00 | `INVOICE` |
| `03-delivery/DC-2026-0209.pdf` | delivered 15/03/2026 | `DELIVERY_PROOF` |
| `04-objection/WRITTEN-OBJECTION-2026-03-24.pdf` | the buyer's written objection | (objection record) |
| `05-whatsapp/chat_defect_day9.txt` | the same objection in chat, day 9 | `WHATSAPP` |
| `05-whatsapp/chat_late_objection.txt` | a negative control: day 60 | `WHATSAPP` |

`chat_late_objection.txt` is deliberately the same story told late. Its
`LATE_COMPLAINT` tag is a suggestion; the engine decides whether the objection
qualifies.

This case matches `contracts/fixtures/case_02.request.json` on dates, amount and
the objection's raised and resolved dates.
