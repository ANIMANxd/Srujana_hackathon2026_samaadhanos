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
