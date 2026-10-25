# SamadhaanOS v4: two options per invoice (hardened architecture)

**Status:** extends `architecture.md` (v3.x). Everything in v3.x stays: the pure legal engine, the contract-first build, Decimal money, offline fixtures, and "nothing auto-sends". This document adds a second path for the supplier and the infrastructure to run it safely.

---

## 0. What the AI-mode conversation got wrong (do not build these)

The two-option idea is good. Several details in that conversation are legally wrong or would get you disqualified for misrepresentation. Fixed here:

| Claim in the conversation | Reality | What we build instead |
|---|---|---|
| "The bank looks at the invoice and pays you in 24 hours." | On TReDS the **buyer must log in and accept** the invoice (the "factoring unit") first. Only then do financiers bid. Without buyer acceptance, nothing happens. | The flow has an explicit **Buyer acceptance** step. That step is also a soft, relationship-friendly ask ("please accept our invoice on TReDS"). |
| "You get 80–90% now, the rest later." | That's classic factoring. On TReDS the supplier receives the **accepted amount minus the discount** (and a platform fee), financed **without recourse** to the supplier. RBI's 2014 TReDS guidelines set settlement at **T+2** from bid acceptance. | `advance_pct` is config: TReDS mode = 100% of the accepted amount minus discount. Settlement days come from config (verify the current rule). |
| "The bank becomes your bad cop and charges the buyer the 3× interest, which it passes back to you." | Once accepted on TReDS, the buyer must pay the financier on the due date. If it defaults, its **bank** reports the default and proceeds against the buyer, without recourse to the supplier. It is **not established** that a financier can claim MSMED s.16 interest or go to the Facilitation Council: the Act's remedies are for a micro or small "supplier". | We claim nothing about the financier enforcing MSMED rights. Open question OQ-10. |
| "Send notices from compliance@samadhaanos.org: 'verified on the SamadhaanOS institutional ledger'." | That impersonates an institution and implies a regulatory status we don't have. Our rules ban it, and the hackathon rules treat fabricated claims as misconduct. | Messages come **from the supplier**, optionally "sent using SamadhaanOS". No compliance persona, no "institutional ledger". |
| "Tell the buyer: 'I don't control the reminders, the bank's system does.'" | That's a scripted lie unless it is literally true. | No scripted excuses. If an invoice really is financed, the honest line is: "This invoice is financed on TReDS, so please pay the financier on the due date." |
| "Your invoices become A-grade collateral and lower your loan rate." | Unsupported. | Removed. |
| "Bank Rate ~6.75% → 20.25%." | The Bank Rate is **5.75%** from 7 Oct 2026, so the s.16 rate is **17.25%**. | The rate comes from engine config, never from prose. |
| "Paying late increases the buyer's tax by ₹3,12,500." | 43B(h) **defers** the deduction to the year the buyer pays. That's a timing effect, not a permanent loss of 25% of the invoice. | The three-line buyer cost from v3 stays. |
| Mock bids from "SBI / HDFC / ICICI", an "Aadhaar-looking" pop-up. | Using real institution names or UIDAI-style branding in a mock is impersonation. | Fictional financiers ("Financier A/B/C"), a clearly labelled **DEMO** eSign with no Aadhaar number collected, and nothing styled like UIDAI or a bank. |

Real-world facts this design relies on (from the RBI TReDS guidelines): the buyer accepts the factoring unit within a window set by TReDS; financing is without recourse to the MSME; after acceptance, the buyer can't dispute quality or claim set-offs; the buyer's bank debits the buyer on the due date in favour of the financier.

---

## 1. The product: two options for every eligible invoice

After the engine evaluates an invoice, the Case screen shows a **choice card** with two options side by side. Both use numbers from deterministic code, and both show their cost honestly.

| | **Option 1: Get paid early** | **Option 2: Recover with the law** |
|---|---|---|
| What happens | The invoice is put on a TReDS-style marketplace. Your buyer accepts it, financiers bid, you pick a bid and sign, and the money arrives. | The existing v3 ladder: balance confirmation, a note to the finance team, a settlement offer, and an evidence pack for the MSME ODR portal. |
| You receive | The accepted amount minus the discount and fee, on settlement day | The principal plus s.16 interest, **if and when** the buyer pays |
| Relationship | Gentle: one ask ("please accept on TReDS"); after that, the buyer pays the financier | Graduated: you choose how firm to be at each step |
| Cost to you | The discount (shown in ₹) | Time and effort. Interest compensates for the delay |
| Works best | **Before the due date**, buyer registered on TReDS, no dispute | **After the due date**, or when the buyer won't accept on TReDS |
| Mocked in this build | eSign, the bid engine, the bank disbursement webhook | Nothing (drafts only; the owner sends them) |

**Never recommend one option.** Show both with numbers and let the owner choose. Copy: "Here's what each path gets you."

### 1.1 Comparison numbers (all from code)
- **Option 1:** `net_receivable = accepted_amount − discount − platform_fee`, with `discount = accepted_amount × bid_rate × tenor_days / 365` (simple, upfront, Decimal, round half-up). Show the effective annual cost.
- **Option 2:** `principal + s16_interest(as_of = expected_payment_date)` from the existing engine. The owner enters the expected payment date (default: today + 30 days, editable). Label it "if paid on <date>".
- **Overdue invoice + Option 1:** show this line: "Financing covers the invoice amount only. The ₹X interest accrued so far isn't included unless your buyer agrees to pay it separately." (Conservative assumption; OQ-11.)

---

## 2. System overview (v4)

```
                ┌──────────────────────── FRONTEND (Next.js) ────────────────────────┐
                │ Dues · Upload & review · Case (choice card) · Get-paid-early flow   │
                │ Recover ladder · Evidence pack · CFO view · Judge console (hidden)  │
                └───────────────▲──────────────────────────────┬─────────────────────┘
                     SSE / poll │                              │ JSON (contract v1.1, additive)
                ┌───────────────┴──────────────────────────────▼─────────────────────┐
                │                         API (FastAPI)                               │
                │  /evaluate-case (v1)   /cases   /cases/{id}/options                │
                │  /cases/{id}/financing/*      /cases/{id}/recovery/*               │
                │  /webhooks/esign   /webhooks/disbursement   /events (SSE)          │
                │  Idempotency · auth stub · rate limits · validation · audit         │
                └──────┬──────────────┬────────────────┬──────────────────┬──────────┘
                       │              │                │                  │
          ┌────────────▼───┐ ┌────────▼───────┐ ┌──────▼────────┐ ┌───────▼─────────┐
          │ ENGINE (pure)  │ │ FINANCE (pure) │ │ WORKFLOW      │ │ STORE (SQLite → │
          │ v3 legal math  │ │ discount, fee, │ │ state machines│ │ Postgres-ready) │
          │ unchanged      │ │ comparison     │ │ track locking │ │ cases, tracks,  │
          └────────────────┘ └────────────────┘ └──────┬────────┘ │ events (hash-   │
                                                       │          │ chained), idem- │
                                ┌──────────────────────▼───────┐  │ potency, webhook│
                                │ PORTS (interfaces)           │  │ inbox           │
                                │ ESignProvider                │  └─────────────────┘
                                │ FinancingMarketplace         │
                                │ DisbursementRail             │
                                │ Clock · IdGenerator          │
                                └───────┬───────────────┬──────┘
                       PROVIDER_MODE=mock│               │PROVIDER_MODE=live (not built)
                ┌────────────────────────▼──┐   ┌────────▼──────────────────────────┐
                │ MOCK PROVIDERS service    │   │ Live adapters (stubs only):        │
                │ (separate FastAPI, :8100) │   │ eSign ASP, TReDS platform API,     │
                │ eSign · bid engine · bank │   │ payout/bank API. Raise             │
                │ Sends REAL signed HTTP    │   │ NotImplementedError.               │
                │ webhooks back to the API  │   └───────────────────────────────────┘
                └───────────────────────────┘
```

**Principle unchanged:** LLM at the edges (extraction only), law at the core. The new FINANCE module is pure Decimal maths, separate from the legal engine, so the legal engine stays frozen.

---

## 3. Repository changes

```
backend/
  engine/                 # UNCHANGED (v3 legal engine)
  finance/                # NEW, pure: discount.py, compare.py, financeability.py
  workflow/               # NEW: state machines, transition tables, track locking
    financing_sm.py  recovery_sm.py  tracks.py
  ports/                  # NEW: interfaces (Protocol classes)
    esign.py  marketplace.py  disbursement.py  clock.py
  adapters/
    mock/                 # client side of the mock providers (HTTP to :8100)
    live/                 # stubs that raise NotImplementedError
  store/                  # NEW: SQLModel models, repositories, migrations
    models.py  repo.py  audit.py  idempotency.py  webhook_inbox.py
  app/
    routes/ cases.py options.py financing.py recovery.py webhooks.py events.py
    security.py (HMAC verify, rate limit)  deps.py (provider wiring, prod guard)
mock_providers/           # NEW separate service, port 8100
  app.py  esign.py  marketplace.py  bank.py  scenarios.py  signer.py
  README.md               # says loudly: SIMULATION ONLY
contracts/                # v1.1 additive: new schemas + fixtures
docs/
  architecture_v4_two_options.md (this file)  state-machines.md  webhooks.md  threat-model.md
```

`make dev` starts three processes: api `:8000`, mock-providers `:8100`, frontend `:3000`.

---

## 4. Domain model and persistence

v3 was stateless. v4 needs state, because financing is a multi-step, asynchronous workflow.

**Store:** SQLite through SQLModel (one file, works offline, zero setup). Keep the schema Postgres-compatible: no SQLite-only types, and money stored as **TEXT** decimal strings, never REAL.

| Table | Key fields | Notes |
|---|---|---|
| `cases` | id (ULID), supplier_ref, buyer_gstin, invoice_no, invoice_date, accepted_amount, delivery_date, input_json, engine_version, config_version, created_at | The engine input is stored verbatim, so results are reproducible |
| `evaluations` | id, case_id, as_of, response_json, engine_version, config_hash | Immutable snapshots |
| `tracks` | id, case_id, kind (`FINANCING`/`RECOVERY`), state, version (optimistic lock), created_at, closed_at | A unique partial index allows only one active track per case |
| `financing_requests` | track_id, accepted_amount, tenor_days, due_date, buyer_acceptance_status, selected_bid_id, esign_session_id, disbursement_ref | |
| `bids` | id, track_id, financier_alias, annual_rate, discount, fee, net_amount, valid_until, status | Fictional financier aliases only |
| `events` | seq, case_id, track_id, type, payload_json, actor (`user`/`system`/`provider:mock-*`), created_at, prev_hash, hash | **Append-only, hash-chained**, so the trail is tamper-evident. It doubles as the evidence ledger for the ODR pack |
| `idempotency_keys` | key, route, request_hash, response_json, created_at | Replays return the stored response; same key + different body → 409 |
| `webhook_inbox` | provider_event_id (unique), provider, received_at, signature_ok, processed_at, outcome | Deduplicates webhooks and keeps a record of every delivery |

**Hash chain:** `hash = sha256(prev_hash || canonical_json(type, payload, actor, created_at))`. `GET /cases/{id}/events/verify` recomputes the chain and reports the first broken link. That's a concrete Implementation and Tech Strategy point: "every action is logged in a tamper-evident trail." Be precise in the pitch: it's tamper-evident, not tamper-proof.

---

## 5. State machines (explicit transition tables, guarded)

### 5.1 Financing track (Option 1)

```
NEW
 └─ check_financeability ─► FINANCEABLE ─┬─► NOT_FINANCEABLE (terminal, with reasons)
                                         │
FINANCEABLE ── request_buyer_acceptance ─► AWAITING_BUYER_ACCEPTANCE
AWAITING_BUYER_ACCEPTANCE ── buyer_accepted ─► BIDDING_OPEN
                          ── buyer_rejected / window_expired ─► BUYER_DECLINED (terminal; offer Option 2)
BIDDING_OPEN ── bids_received(n≥1) ─► BIDS_AVAILABLE
             ── bidding_closed(n=0) ─► NO_BIDS (terminal; offer Option 2)
BIDS_AVAILABLE ── select_bid ─► AWAITING_ESIGN       (guard: bid not expired)
               ── bids_expired ─► BIDDING_OPEN        (re-open once, then NO_BIDS)
AWAITING_ESIGN ── esign_completed (webhook) ─► AWAITING_DISBURSEMENT
               ── esign_failed / expired ─► BIDS_AVAILABLE (max 3 attempts, then CANCELLED)
AWAITING_DISBURSEMENT ── payout.processed (webhook) ─► DISBURSED
                      ── payout.failed (webhook) ─► DISBURSEMENT_FAILED ─ retry ─► AWAITING_DISBURSEMENT
DISBURSED ── due_date_reached + buyer_paid_financier ─► SETTLED (terminal)
          ── buyer_default ─► SETTLED_WITHOUT_RECOURSE (terminal; financier's issue, supplier keeps the money)
Any pre-signature state ── user_cancel ─► CANCELLED (terminal)
```

### 5.2 Recovery track (Option 2): the v3 ladder, now with state

`NEW → STAGE_1_PREPARED → STAGE_1_SENT_BY_OWNER → STAGE_2_PREPARED → … → STAGE_4_PACK_READY → ODR_FILED_BY_OWNER (recorded) → PAID / SETTLED / CLOSED`.
"SENT_BY_OWNER" is recorded only when the owner taps "I've sent it". We never send anything.

### 5.3 Track locking rules (the hard part; test every row)

| From | To | Allowed? | Why |
|---|---|---|---|
| No track | Financing | If financeable | |
| No track | Recovery | If the engine says eligible, or always for basic reminders | |
| Recovery (any stage before Stage 3) | Financing | Yes, if financeable → recovery is **paused**, not deleted | A gentle reminder doesn't stop a buyer accepting on TReDS |
| Recovery Stage 3 or 4 | Financing | **No** | Once a dispute is formal, financing is unrealistic; the engine flags it as a dispute |
| Financing before AWAITING_ESIGN | Recovery | Yes → financing is cancelled | Nothing assigned yet |
| Financing AWAITING_ESIGN or later | Recovery | **No** | After signature the receivable belongs to the financier. Recovery actions would be wrong and confusing |
| Financing BUYER_DECLINED / NO_BIDS / CANCELLED | Recovery | Yes, one-click "Switch to Option 2" | |

Guards are enforced in `workflow/tracks.py` **and** by the database (unique partial index plus an optimistic `version` check). A race between two tabs must produce exactly one winner and a 409 for the loser.

### 5.4 Financeability check (pure function, `finance/financeability.py`)
Inputs: the engine output plus case facts. Not financeable if any of these is true:
- the engine gate failed (not micro/small, trader, Udyam after supply);
- a written objection or dispute is recorded;
- recovery is at Stage 3 or later;
- the amount is below `financing.min_amount`;
- the buyer is flagged as not on TReDS **and** the user declines to invite it;
- the due date has passed by more than `financing.max_overdue_days` (config, default 0 = only before the due date; OQ-11).

Return the reasons as codes with plain-English messages, exactly like the engine's warnings.

---

## 6. Ports and adapters (how mocks become real later)

```python
class ESignProvider(Protocol):
    def create_session(self, doc: SignableDoc, signer: SignerRef, idem_key: str) -> ESignSession: ...
    def get_session(self, session_id: str) -> ESignSession: ...
    # completion arrives via signed webhook → /webhooks/esign

class FinancingMarketplace(Protocol):
    def register_invoice(self, inv: FactoringUnitIn, idem_key: str) -> FactoringUnitRef: ...
    def request_buyer_acceptance(self, ref: FactoringUnitRef) -> AcceptanceRequest: ...
    def get_acceptance(self, ref: FactoringUnitRef) -> AcceptanceStatus: ...
    def open_bidding(self, ref: FactoringUnitRef, window: timedelta) -> None: ...
    def list_bids(self, ref: FactoringUnitRef) -> list[Bid]: ...
    def accept_bid(self, ref: FactoringUnitRef, bid_id: str, idem_key: str) -> BidAcceptance: ...

class DisbursementRail(Protocol):
    # payout status arrives via signed webhook → /webhooks/disbursement
    def get_payout(self, payout_ref: str) -> PayoutStatus: ...

class Clock(Protocol):
    def now(self) -> datetime: ...   # FrozenClock / OffsetClock in demo and tests
```

Wiring in `app/deps.py`, driven by env:
- `PROVIDER_MODE=mock` → `adapters/mock/*` (HTTP to `MOCK_PROVIDERS_URL`).
- `PROVIDER_MODE=live` → `adapters/live/*` (stubs that raise `NotImplementedError("live provider not integrated")`).
- **Production guard:** if `APP_ENV=production` and any adapter is a mock, the app **refuses to start**. If `APP_ENV != production`, every API response carries the header `X-Simulation: true`, and the UI shows a DEMO badge on all Option 1 screens.

Real-world mapping (docs and pitch only, never in the UI as if live): eSign via a licensed eSign service provider under the IT Act; marketplace = one of the RBI-authorised TReDS platforms; disbursement via the financier's bank and the platform's settlement files. Say "would integrate with", not "integrated with".

---

## 7. Mock providers (separate service, port 8100, "high-fidelity mocks")

All three behave like real asynchronous providers: they return immediately with a pending status, then send a **real, signed HTTP webhook** back to the API after a delay. That gives the webhook security, idempotency and state machine real traffic to handle.

### 7.1 Mock eSign
- `POST /esign/sessions` → `{session_id, status:"PENDING", signing_url:"/mock/esign/<id>", expires_at}`.
- The signing page (rendered by our frontend, not a copy of any real page) shows: the document summary, "**DEMO eSign: simulated. No Aadhaar number is collected or stored.**", one OTP box. Accepted OTP: `MOCK_ESIGN_OTP` (default `123456`). 3 attempts, then `FAILED`. The session expires after 10 minutes.
- On success → webhook `esign.completed` `{session_id, signed_doc_sha256, signer_display:"Demo Signer", signed_at}`. The "signed" PDF gets a visible **SIMULATED SIGNATURE** stamp and the document hash.
- Never accept or store an Aadhaar number, not even a fake one. The field doesn't exist.

**What gets signed:** a **"Financing request and assignment consent (DEMO TEMPLATE)"** generated by `backend/artifacts/`: parties (fictional), invoice reference, accepted amount, selected bid, discount and net amount, and the statement "Without recourse to the supplier, per the platform's terms (template; actual terms are set by the TReDS platform)". It is watermarked TEMPLATE, and every party name is fictional in demo data.

### 7.2 Mock TReDS-style bid engine
- `POST /marketplace/factoring-units` → registers the unit (idempotent on `invoice_no + buyer_gstin`).
- `POST /marketplace/factoring-units/{id}/acceptance-request` → simulates the buyer. The default scenario auto-accepts after `MOCK_BUYER_ACCEPT_DELAY_S` (default 3s) and sends webhook `fu.accepted`; other scenarios reject or expire.
- `POST /marketplace/factoring-units/{id}/bidding` → after `MOCK_BID_DELAY_S`, generates **3 bids** from fictional financiers "Financier A/B/C":
  - Rates are drawn **deterministically**: the seed is `sha256(case_id + scenario)`, the band comes from config `mock_financing.rate_band` (e.g. 8.00%–12.00%, labelled illustrative), quantized to 0.05%.
  - The fee comes from config `mock_financing.platform_fee_pct` (illustrative).
  - Each bid: `{bid_id, financier_alias, annual_rate, discount, fee, net_amount, valid_until}`, where **discount and net are computed by our `finance/discount.py`**, not by the mock, so the mock can't introduce maths bugs.
  - Webhook `bids.available`.
- `POST /marketplace/bids/{bid_id}/accept` → idempotent; webhook `bid.accepted`.

### 7.3 Mock bank disbursement webhook
- After `esign.completed` and `bid.accepted`, the mock bank schedules a payout: webhook `payout.processed` `{payout_id, amount, currency:"INR", utr:"MOCKUTR…", settled_at}` after `MOCK_PAYOUT_DELAY_S` (simulating T+N; the label says "simulated settlement").
- UTRs and IDs always carry the `MOCK` prefix, so they can never be mistaken for real references.

### 7.4 Scenario injection (judge console → mock providers)
`POST /mock/scenarios` with `{case_id, scenario}`. Supported scenarios:
`happy_path` · `buyer_rejects` · `buyer_window_expires` · `no_bids` · `bids_expire` · `esign_wrong_otp` · `esign_expires` · `webhook_duplicate` (sends the same event 3 times) · `webhook_out_of_order` (payout before esign) · `webhook_bad_signature` · `webhook_delayed` (30s, plus retries) · `payout_failed_then_succeeds` · `buyer_defaults_after_disbursal`.

During the demo, run `happy_path` once, then `webhook_duplicate` or `buyer_rejects` to show it doesn't break. This is the strongest "robustness" moment in the whole demo.

---

## 8. Hardening checklist

**Webhooks (`docs/webhooks.md`)**
- Headers: `X-Mock-Event-Id`, `X-Mock-Timestamp`, `X-Mock-Signature: v1=<hex>`, where the signature is HMAC-SHA256 over `timestamp + "." + raw_body` with `WEBHOOK_SECRET_<PROVIDER>`.
- Verify against the **raw bytes** before parsing. Use a constant-time compare. Reject if the timestamp is more than 300s old (replay protection).
- Insert into `webhook_inbox` keyed by `provider_event_id`. A duplicate returns **200 with `{"duplicate": true}`** and has no side effects.
- The state transition happens in the same DB transaction as the inbox insert. An event that isn't valid for the current state (out of order) is **stored and parked**, not applied, and is re-evaluated when the state catches up. After a timeout, it is flagged for review.
- Always answer fast (2xx for handled or duplicate, 401 for a bad signature, 422 for a malformed body). The mock sender retries on non-2xx with backoff 1s, 2s, 4s, 8s, 16s, then dead-letters the event.

**API**
- An `Idempotency-Key` header is **required** on every mutating POST under `/financing` and `/recovery`. The same key with a different body hash returns 409.
- Optimistic locking: clients send `If-Match: <track.version>`. A stale version returns 409 with the current state.
- Validation: Pydantic v2 strict models, Decimal strings with max 2 dp, positive amounts, dates not in the far future, GSTIN format (and checksum if implemented).
- Uploads (extraction): PDF only (check the magic bytes, not just the extension), max 10 MB, max 20 pages, processed in a temp dir and then deleted.
- Rate limits: OTP attempts per session (3), scenario injection only when `APP_ENV != production`, and an in-memory token bucket on mutation routes.
- CORS locked to the frontend origin. Secrets only from env; `.env.example` has placeholders.
- Errors use one envelope: `{"error":{"code","message","details"}}`. Messages are plain English; no stack traces in responses.

**Data and privacy**
- No Aadhaar data, ever. Contact person phone and email are personal data: store them only when needed, show them masked in logs, and note the DPDP Act as a production requirement in the README.
- Demo data is fully synthetic (names, GSTINs with valid format but fictional, phones like `+91 90000 0000x`).

**Correctness**
- Money is Decimal end to end and TEXT in the DB. The finance maths has its own spec tests, written by the independent test author, with hand-computed values.
- Time: all workflow code takes a `Clock`. The judge console can **advance simulated time** ("jump to day 46") to show the switch from Option 1 to Option 2. The engine already takes `as_of`.
- Determinism: mock outputs are seeded by case and scenario, so the same demo gives the same bids every time.

**Observability**
- Structured JSON logs with `correlation_id` (from the request header, or generated and propagated to the mock calls and webhooks).
- `/health` reports DB, mock providers reachable, provider mode, and config version.
- `/cases/{id}/events` lists the timeline from the hash-chained log, and `/events/verify` checks the chain.

**Threat model (`docs/threat-model.md`, short)**: forged webhook (HMAC + timestamp), replayed webhook (inbox dedupe + tolerance), double submit (idempotency), race between tabs (optimistic lock + unique index), mocks in production (startup guard), tampered audit trail (hash chain), malicious upload (MIME, size and page limits), PII leakage (masking, minimal storage).

---

## 9. Contract v1.1 (additive only)

New endpoints (all under `/api/v1`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/cases` | Create a case from approved fields (after extraction review) → runs the engine, stores the evaluation |
| GET | `/cases/{id}` | Case, latest evaluation, active track, available actions |
| GET | `/cases/{id}/options?expected_payment_date=` | **The two-option comparison** |
| POST | `/cases/{id}/financing` | Start the financing track (financeability check runs first) |
| POST | `/cases/{id}/financing/buyer-acceptance` | Ask the buyer to accept (mock) |
| GET | `/cases/{id}/financing/bids` | List bids |
| POST | `/cases/{id}/financing/bids/{bid_id}/select` | Select a bid → creates the eSign session |
| POST | `/cases/{id}/financing/cancel` | Cancel before signature |
| POST | `/cases/{id}/recovery` | Start or resume recovery; `{stage}` → prepares a draft (v3 artifacts) |
| POST | `/cases/{id}/recovery/mark-sent` | The owner confirms they sent it |
| POST | `/webhooks/esign`, `/webhooks/marketplace`, `/webhooks/disbursement` | Signed webhooks from the providers |
| GET | `/cases/{id}/events` · `/cases/{id}/events/verify` · `/cases/{id}/stream` (SSE) | Timeline, chain check, live updates |
| POST | `/mock/scenarios`, `/mock/clock` | Judge console only, disabled in production |

`GET /cases/{id}/options` response (abridged; example uses a 30-day tenor, an illustrative 8–12% band and a 0.10% fee: 12% → discount ₹12,328.77, 8% → ₹8,219.18):

```json
{
  "case_id": "01J…",
  "as_of": "2026-10-25",
  "simulation": true,
  "get_paid_early": {
    "available": true,
    "unavailable_reasons": [],
    "indicative": {
      "accepted_amount": "1250000.00",
      "tenor_days": 30,
      "rate_band_pct": {"low": "8.00", "high": "12.00", "label": "illustrative"},
      "platform_fee_pct": "0.10",
      "net_receivable_range": {"low": "1236421.23", "high": "1240530.82"},
      "settlement": "T+2 after bid acceptance (config)"
    },
    "notes": ["Your buyer must accept the invoice on the platform first.",
              "Interest accrued so far is not included."],
    "citations": [{"source": "RBI TReDS guidelines", "ref": "config:treds.guidelines"}]
  },
  "recover_with_law": {
    "available": true,
    "expected_payment_date": "2026-11-24",
    "principal": "1250000.00",
    "interest_to_expected_date": "…",
    "total_if_paid": "…",
    "current_stage": "STAGE_1",
    "notes": ["Only received if the buyer pays.", "You send every message yourself."],
    "citations": [{"source": "MSMED Act s.16", "ref": "config:interest_multiplier"}]
  },
  "recommendation": null
}
```

`recommendation` is always `null`. It's there so that nobody "helpfully" adds one later. A spec test asserts that it stays null.

New config keys (each `{value, source_ref, verified, note}`): `treds.buyer_acceptance_required` (true, RBI guidelines), `treds.without_recourse` (true), `treds.settlement_days` (2 per the 2014 guidelines; verify the current rule), `financing.day_count` (365), `financing.min_amount`, `financing.max_overdue_days` (0), `financing.advance_pct` (100 for TReDS mode), `mock_financing.rate_band` (illustrative), `mock_financing.platform_fee_pct` (illustrative).

---

## 10. Frontend changes (extends `frontend-structure.md`)

**Case screen:** below the guidance card, a **choice card** with two columns ("Get paid early" | "Recover with the law"), each showing the one big number, one line on what happens, one line on the cost, and a button. The DEMO badge appears on the Option 1 column. Disabled options show their reason in one line ("Your buyer declined on the platform → use Option 2").

**New route `/case/[id]/early`** (the Get-paid-early flow), a vertical stepper driven entirely by `track.state` from the server:
1. **Check**: financeable ✓ (or the reasons, plus "Use Option 2").
2. **Ask your buyer**: an explanation and a draft message to the buyer ("Could you accept invoice INV-0042 on TReDS? It lets us get paid early at no cost to you."), plus the status *Waiting for buyer… / Accepted ✓ / Declined*.
3. **Choose a bid**: 3 bid cards (Financier A/B/C), each with rate, discount ₹, fee ₹, **you receive ₹**, and valid until. Sorted by what you receive. No "best" badge; just sorted.
4. **Sign**: the DEMO eSign modal (OTP only, banner "simulated, no Aadhaar data").
5. **Money on the way → Received**: settlement status, MOCK UTR, amount. It updates live via SSE, with a 3s polling fallback.
6. **After**: "Your buyer now pays the financier on <due date>. Recovery actions are locked for this invoice." A timeline entry is added.

**Recovery (Option 2)** = the existing ladder plus "I've sent it" tracking.

**Judge console additions:** a scenario picker, "advance clock by N days", "verify audit chain", and a toggle that shows raw webhook deliveries (accepted / duplicate / rejected), which is good for the technical judges.

**Copy rules:** never "instant cash", "guaranteed", "bad cop", "shield", "institutional ledger". Use "get paid early", "your buyer accepts on TReDS", "financed without recourse to you (per the platform's terms)".

---

## 11. Testing (add to v3 tests)

| Suite | Owner | Covers |
|---|---|---|
| `tests/spec/finance/` | Independent test author | Discount, fee and net with hand-computed values; rounding; tenor edge cases (1 day, 365 days); `recommendation` always null |
| `tests/dev/workflow/` | Engine/API | Every allowed and forbidden transition in section 5; every row of the track-locking table |
| `tests/dev/webhooks/` | API | Valid signature; bad signature → 401; stale timestamp → 401; duplicate → no side effect; out-of-order → parked, then applied; retries → applied exactly once |
| `tests/dev/idempotency/` | API | Same key + same body → same response; same key + different body → 409 |
| `tests/dev/concurrency/` | API | Two concurrent bid selections → one 200, one 409 |
| `tests/dev/audit/` | API | The chain verifies; editing one event row → verify reports that seq |
| `tests/contract/` | API | v1 responses unchanged; v1.1 schemas match `contracts/` |
| `tests/e2e/` (Playwright, optional) | Frontend | The happy path end to end through the mock providers; the `buyer_rejects` scenario switches to Option 2 |
| Startup guard test | API | `APP_ENV=production` + mock adapter → the app exits non-zero |

---

## 12. Open questions (add to `docs/open-questions.md`)

| ID | Question | Default until resolved |
|---|---|---|
| OQ-10 | Can a financier or factor (as assignee) claim MSMED s.16 interest or refer to the MSEFC? | Assume **no**. Never claim it in UI or pitch |
| OQ-11 | Can an already-overdue invoice be financed on TReDS, and what happens to the interest accrued before financing? | Default: financing only before the due date (`max_overdue_days=0`); show the interest-not-included note |
| OQ-12 | The current TReDS settlement timeline (2014 guidelines say T+2) and any newer RBI circular | Config value, `verified=false` until checked |
| OQ-13 | Is the turnover threshold for mandatory TReDS onboarding of buyers ₹250 cr (MSME Ministry notification) still current? | Mention only with a source |
| OQ-14 | Factoring Regulation Act: notice of assignment and registration of the assignment with the Central Registry (on TReDS this is handled by the platform) | The demo template says "per platform terms"; no legal claim |

---

## 13. How to explain it in one breath (pitch)

"Every eligible invoice gets two options. **Get paid early**: your buyer accepts the invoice on TReDS, financiers bid, you sign, and the money arrives without recourse to you. **Recover with the law**: if they won't, our engine calculates exactly what you're owed and walks you through the gentlest effective next step. The bank integrations are simulated today behind the same interfaces a real provider would plug into. The legal maths is real, tested and cited."

Say "simulated" out loud. Judges reward honesty about mocks; they punish discovering it.
