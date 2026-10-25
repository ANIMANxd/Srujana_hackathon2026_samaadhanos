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

## Where the numbers come from

**Option 1 (financing) is computed by `backend/finance`.** `discount`, `fee` and `net_receivable`
come from `backend/finance/discount.py`; the options card comes from
`backend/finance/compare.py::compare_options`; each bid comes from `bid_quote`. The mock providers
never compute a rupee — they only pick rates.

The inputs are config, not market data: the rate band and platform fee are
`mock_financing.rate_band` / `mock_financing.platform_fee_pct`, labelled `illustrative`, and the
day count is `financing.day_count`. **The rates are illustrative; the arithmetic is real.** That is
why no fixture is marked a placeholder any more.

The tenor is **as-of → due date**, not a chosen number. For the demo case that is 4 days
(2026-10-25 → 2026-10-29), and at a 4-day tenor the flat platform fee (₹1,250.00) is larger than
the discount — a real property of short tenors, and the reason nothing here may be hard-coded.

| Rate | Discount | Fee | You receive |
|---|---|---|---|
| 8.00% (Financier B, selected) | ₹1,095.89 | ₹1,250.00 | **₹12,47,654.11** |
| 10.00% (Financier C) | ₹1,369.86 | ₹1,250.00 | **₹12,47,380.14** |
| 12.00% (Financier A) | ₹1,643.84 | ₹1,250.00 | **₹12,47,106.16** |

**Option 2 (recovery) numbers are engine output.** `interest_to_expected_date` and `total_if_paid`
come from the frozen engine through the `interest_to_date` callable that `compare_options` is given;
finance never reimplements s.16. As of 2026-11-24 the engine says interest ₹14,768.84 and total claim
₹12,64,768.84.

**`recommendation` is `null`** in the schema and in every fixture (golden rule 20). Two tests assert it.

### When B2 becomes redundant

`backend/finance/` **is** B2. If a number here ever disagrees with the module, the module wins and
this folder is stale — regenerate rather than edit.

