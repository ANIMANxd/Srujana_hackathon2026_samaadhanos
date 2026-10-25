# Webhooks (v4)

Concise extract of `docs/architecture_v4_two_options.md` section 8 ("Webhooks"). The providers
that send these events are the mock services in `mock_providers/` (port 8100); they are
simulations and must never be described as live integrations.

## 1. Envelope and signature

```
X-Mock-Event-Id:   <unique per event>
X-Mock-Timestamp:  <unix seconds>
X-Mock-Signature:  v1=<hex>
```

The signature is **HMAC-SHA256 over `timestamp + "." + raw_body`**, keyed by
`WEBHOOK_SECRET_<PROVIDER>` from the environment.

## 2. Verification order (do not reorder)

1. Read the **raw bytes**. Verify the signature over those bytes **before** parsing the body.
   Parsing first is a listed trap in `AGENTS.md` section 7.
2. Compare signatures with a **constant-time** comparison.
3. Reject when the timestamp is more than **300 s** old (replay protection).
4. Only then parse and validate the payload.

## 3. Delivery semantics

| Situation | Response |
|---|---|
| Handled | `2xx` |
| Duplicate `provider_event_id` | `200` with `{"duplicate": true}`, **no side effects** |
| Bad signature | `401` |
| Malformed body | `422` |

The sender retries on any non-`2xx` with backoff **1s, 2s, 4s, 8s, 16s**, then dead-letters the event.

## 4. Duplicates and ordering

- Every delivery is inserted into `webhook_inbox`, keyed by the unique `provider_event_id`
  (`provider, received_at, signature_ok, processed_at, outcome`).
- The state transition happens **in the same database transaction** as the inbox insert, so a
  crash can never apply an event without recording it.
- An event that is not valid for the current state (out of order) is **stored and parked**, not
  applied, and is re-evaluated when the state catches up. After a timeout it is flagged for review.
  Applying an out-of-order event is a listed trap.

## 5. Endpoints

| Path | Sender | Events |
|---|---|---|
| `POST /api/v1/webhooks/esign` | mock eSign | `esign.completed` |
| `POST /api/v1/webhooks/marketplace` | mock bid engine | `fu.accepted`, `bids.available`, `bid.accepted` |
| `POST /api/v1/webhooks/disbursement` | mock bank | `payout.processed`, `payout.failed` |

Each event type maps onto exactly one allowed transition in `docs/state-machines.md`. An event
with no matching transition is parked, never force-applied.

## 6. Demo and safety

- Providers run in `PROVIDER_MODE=mock` with `X-Simulation: true` on API responses, and every
  identifier (`payout_id`, `utr`, session ids) carries a `MOCK` prefix so it cannot be mistaken
  for a real reference.
- Financier aliases are fictional ("Financier A/B/C"); no real bank or TReDS platform name
  appears in a payload, a UI screen or demo data (golden rule 17).
- Scenario injection (`POST /mock/scenarios`) can force `webhook_duplicate`,
  `webhook_out_of_order`, `webhook_bad_signature` and `webhook_delayed`; it is disabled when
  `APP_ENV=production`. These are the rehearsals that prove the rules above actually hold.
