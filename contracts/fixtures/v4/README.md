# contract v1.1 fixtures (v4 two-option model)

Examples for the schemas in `backend/app/schemas_v4.py`, published in
`contracts/openapi.json` and `contracts/types.ts`. Source of truth for every shape is
`docs/architecture_v4_two_options.md` sections 4, 5 and 9.

## Do not hand-edit these files

```bash
python -m backend.app.export_v4_fixtures
```

The generator exists for three reasons:

1. the eight financing states describe **one** case, so they are built from a single `Case`
   object and cannot drift apart;
2. the audit `Event` list must carry a **valid hash chain**, so
   `hash = sha256(prev_hash || canonical_json(type, payload, actor, created_at))` is computed,
   not typed (genesis `prev_hash` is 64 zeros);
3. the Option 2 figures are **engine output**, read from `backend.engine.evaluate.evaluate_case`
   at the two `expected_payment_date`s the cards describe (golden rule 7).

`backend/tests/contract/test_contract_v1_1.py` re-validates every payload against its model,
recomputes the chain, and checks that tampering with one event is detectable.

## File layout

Every file is `{"_fixture": {...provenance...}, "payload": <the example>}`. The provenance block
carries `schema`, `contract_version`, `synthetic`, `placeholder`, `placeholder_fields`, `why` and
`regenerate_with`.

| File | Schema | What it shows |
|---|---|---|
| `options-financeable.json` | `OptionsResponse` | Both options available, pre-due date. As-of 2026-10-25, expected payment 2026-11-24 |
| `options-not-financeable-overdue.json` | `OptionsResponse` | Option 1 blocked because the due date passed (`financing.max_overdue_days = 0`, OQ-11); Option 2 still available |
| `case-detail-FINANCEABLE.json` | `CaseDetail` | Track created, financeability passed |
| `case-detail-AWAITING_BUYER_ACCEPTANCE.json` | `CaseDetail` | Waiting on the buyer on the platform |
| `case-detail-BIDS_AVAILABLE.json` | `CaseDetail` | Three bids in, none chosen |
| `case-detail-AWAITING_ESIGN.json` | `CaseDetail` | Bid selected; recovery is **locked** from here (`docs/state-machines.md` §3) |
| `case-detail-AWAITING_DISBURSEMENT.json` | `CaseDetail` | Signed, waiting on the payout webhook |
| `case-detail-DISBURSED.json` | `CaseDetail` | Money received; buyer now pays the financier |
| `case-detail-BUYER_DECLINED.json` | `CaseDetail` | Terminal; "Switch to Option 2" offered |
| `case-detail-NO_BIDS.json` | `CaseDetail` | Terminal; "Switch to Option 2" offered |
| `bids.json` | `Bid[]` | Financier A/B/C. Fictional aliases only (golden rule 17) |
| `esign-session.json` | `ESignSession` | Signed demo session. No Aadhaar field exists (golden rule 18) |
| `payout.json` | `PayoutStatus` | `MOCKUTR…` so it can never read as a real reference |
| `events.json` | `Event[]` | 12-event chain from `case.created` to `financing.disbursed` |
| `chain-verify-result.json` | `ChainVerifyResult` | The result of verifying `events.json` |
| `webhook-deliveries.json` | `WebhookDelivery[]` | Applied, duplicate (no side effects), parked (out of order), rejected (bad signature) |
| `v1-contract-baseline.json` | *(not a contract type)* | SHA-256 fingerprint of every v1.0 component and path, captured at tag time |

## What is a placeholder, and why

**Option 1 (financing) numbers are placeholders.** `backend/finance/` (B2) does not exist yet, so
`discount`, `fee`, `net_amount`, `annual_rate`, the rate band and the platform fee are
hand-computed with the architecture_v4 §1.1 formula:

```
discount = accepted_amount × annual_rate × tenor_days / 365     (half-up, 2 dp)
fee      = accepted_amount × platform_fee_pct
net      = accepted_amount − discount − fee
```

For the demo case (₹12,50,000 accepted, 30-day tenor, 0.10% fee):

| Rate | Discount | Fee | You receive |
|---|---|---|---|
| 8.00% (Financier B) | ₹8,219.18 | ₹1,250.00 | **₹12,40,530.82** |
| 10.25% (Financier C) | ₹10,530.82 | ₹1,250.00 | **₹12,38,219.18** |
| 12.00% (Financier A) | ₹12,328.77 | ₹1,250.00 | **₹12,36,421.23** |

These match the worked example in architecture_v4 §9. They are still **placeholders**: they are
not market rates, and when B2 lands the numbers must come from `backend/finance/` and the
`_fixture.placeholder` flag must be set to `false`. Every such file names the affected fields in
`_fixture.placeholder_fields`.

**Option 1 is never a recommendation.** `recommendation` is typed `null` in the schema and is
`null` in every fixture (golden rule 20). A test asserts both.

**Option 2 (recovery) numbers are real.** `interest_to_expected_date` and `total_if_paid` come
from the frozen engine at the stated `expected_payment_date`, so they are not placeholders and
must not be adjusted by hand.
