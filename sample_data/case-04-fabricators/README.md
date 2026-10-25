# Case 04 - Sample Fabricators Pvt Ltd

An invoice with an ambiguous date (10/03/2026) and a part payment recorded on
15/05/2026.

| Document | What it proves | Evidence kind |
|---|---|---|
| `01-purchase-order/PO-2026-0310.pdf` | the order | `PO` |
| `02-tax-invoice/INV-2026-0310.pdf` | the payable, 5,00,000.00 | `INVOICE` |
| `03-payment/REMITTANCE-ADVICE-2026-05-15.pdf` | 1,50,000.00 paid, 3,50,000.00 left | (part payment) |

There is no delivery challan here on purpose: case 04's delivery proof in the
preset is an LR, which is not in this corpus yet. Upload only what you hold.

This case matches `contracts/fixtures/case_04.request.json` on dates, amount and
the part-payment date and amount.
