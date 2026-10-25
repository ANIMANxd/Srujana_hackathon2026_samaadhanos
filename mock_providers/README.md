# Mock providers — **SIMULATION ONLY. Fictional names. No real money, no real signatures, no Aadhaar data.**

A separate FastAPI service on **port 8100**, started by `make mock` (or by `make dev`
alongside the API and the frontend). It imports **nothing** from `backend/`: it is a
standalone simulation, and it must be impossible for it to reach a legal rule, a
config constant or the database.

## Why it exists

The API's webhook pipeline — signature verification, inbox dedupe, parking
out-of-order events, replay protection — is only trustworthy if something actually
attacks it. This service sends **real signed HTTP webhooks** with real retries, so the
API is tested by traffic rather than by a mock of traffic.

## Modules

| File | What it does |
|---|---|
| `app.py` | The FastAPI app: `/health`, `POST /mock/reset`, `GET /mock/deliveries`, routers, the simulation banner and the production refusal |
| `signer.py` | `v1=<hex>` HMAC-SHA256 over `timestamp + "." + raw_body`; `MOCK`-prefixed ULIDs |
| `delivery.py` | Builds the envelope, signs it, POSTs it, retries, dead-letters |
| `esign.py` | Session → test OTP → `esign.completed` webhook. No Aadhaar field exists |
| `marketplace.py` | Buyer acceptance, then three fictional financiers' bids |
| `bank.py` | A payout with a `MOCK` UTR |
| `scenarios.py` | Judge-console scenario injection |
| `state.py` | In-memory dicts, cleared by `POST /mock/reset` |

## The delivery contract

Every event is

```json
{ "event_id": "MOCK_EVT_<ulid>", "type": "esign.completed", "created_at": "...", "data": { ... } }
```

sent with

```
X-Mock-Event-Id:   MOCK_EVT_…
X-Mock-Timestamp:  <unix seconds>
X-Mock-Signature:  v1=<hex hmac_sha256(secret, timestamp + "." + raw_body)>
X-Simulation:      true
```

where the secret is `WEBHOOK_SECRET_<PROVIDER>`. Retries on non-2xx: **1, 2, 4, 8, 16 s**,
then the event is appended to `dead_letter.jsonl` and to `GET /mock/deliveries`.

A fixed test vector lives in `docs/webhooks.md`, and both this service and the API
assert against it, so the two implementations are proved to agree without sharing code.

## Scenarios (architecture_v4 section 7.4)

`POST /mock/scenarios {case_id, scenario}` activates one for a case and records that
case as the **active case**, which is how outgoing webhooks are routed when the API
adapter sends no case id of its own. `GET /mock/scenarios/{case_id}` reports what is
active; `GET /mock/scenarios` lists the menu.

Every row below is run **end to end against the live API** by
`mock_providers/tests/test_scenarios_e2e.py` (two real uvicorn processes, real signed
webhooks), and the assertion is the final track state that section 5.1 predicts.

| Scenario | What the mock does | End state (§5.1) |
|---|---|---|
| `happy_path` | Buyer accepts, three bids, OTP completes, payout settles | **DISBURSED** |
| `buyer_rejects` | `fu.rejected` instead of `fu.accepted` | **BUYER_DECLINED** (terminal; Option 2 offered) |
| `buyer_window_expires` | `fu.expired` — the window closes with no decision | **BUYER_DECLINED** (terminal) |
| `no_bids` | The bidding window closes with zero bids (`bidding.closed`) | **NO_BIDS** (terminal) |
| `bids_expire` | Three bids are announced, then `bids.expired` | **BIDDING_OPEN** (re-opened once; a second expiry is what reaches `NO_BIDS`) |
| `esign_wrong_otp` | Every OTP is rejected; three failures send `esign.failed` | **BIDS_AVAILABLE** (back to bid selection) |
| `esign_expires` | The session opens already past its 10-minute window | **BIDS_AVAILABLE** |
| `webhook_duplicate` | `esign.completed` is sent three times with the same signed body | **AWAITING_DISBURSEMENT** → **DISBURSED** once the payout lands; exactly one transition, never three |
| `webhook_out_of_order` | The payout is announced *before* the signature | **DISBURSED** (the payout is parked, then applied when the signature arrives) |
| `webhook_bad_signature` | `esign.completed` is signed with the wrong secret | **AWAITING_ESIGN** (401; nothing applied, nothing stored) |
| `webhook_delayed` | `esign.completed` arrives after `MOCK_DELAYED_S` (30 s by default) | **AWAITING_DISBURSEMENT** → **DISBURSED** |
| `payout_failed_then_succeeds` | `payout.failed`, then `payout.retry`, then `payout.processed` | **DISBURSED** (via `DISBURSEMENT_FAILED`) |
| `buyer_defaults_after_disbursal` | After the payout, `buyer.default` | **SETTLED_WITHOUT_RECOURSE** (terminal; the financier's issue, the supplier keeps the money) |

Two of these accept an intermediate state in the assertion (`AWAITING_DISBURSEMENT`
or `DISBURSED`) because the payout webhook and the check race by design; the table
states the settled end state.

## `GET /mock/deliveries`

The last 50 deliveries, newest first, each with `status` (`DELIVERED`,
`DEAD_LETTER` or `PENDING`), `attempt_count`, the target URL and every attempt's
status code. Dead letters are listed separately. This is what the judge console
points at to show a retry actually happened.

## Honest limits

- In-memory state. A restart forgets every unit, session and payout; that is fine for
  a demo and wrong for anything else.
- Delivery is a FastAPI `BackgroundTask`, so it runs after the response and dies with
  the process. A real provider would use a queue.
- The marketplace picks rates deterministically from the invoice, inside an
  illustrative band. It does **not** compute discount, fee or net: `backend/finance/`
  owns every rupee, so a simulation cannot introduce a money bug.
- The bank never moves money. `MOCKUTR…` is a string, nothing more.
- `APP_ENV=production` makes the service refuse to start.
