# State machines (v4)

Concise extract of `docs/architecture_v4_two_options.md` section 5. The full design, rationale and
the repo layout are in that document; this file is the reference for implementers and reviewers.
Guard code lives in `backend/workflow/` (planned: `financing_sm.py`, `recovery_sm.py`, `tracks.py`).

Two tracks run against one case. A case has at most **one active track** at a time.

## 1. Financing track (Option 1)

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

Two webhook-driven edges (`esign_completed`, `payout.processed`) and one external one
(`buyer_accepted`) are the only transitions the API does not initiate itself. Their delivery
rules are in `docs/webhooks.md`.

## 2. Recovery track (Option 2): the v3 ladder, now with state

```
NEW → STAGE_1_PREPARED → STAGE_1_SENT_BY_OWNER → STAGE_2_PREPARED → … 
    → STAGE_4_PACK_READY → ODR_FILED_BY_OWNER (recorded) → PAID / SETTLED / CLOSED
```

`SENT_BY_OWNER` is recorded only when the owner taps "I've sent it". **Nothing auto-sends**
(golden rule 10); the state records the owner's claim, not a delivery.

## 3. Track locking rules (test every row)

| From | To | Allowed? | Why |
|---|---|---|---|
| No track | Financing | If financeable | |
| No track | Recovery | If the engine says eligible, or always for basic reminders | |
| Recovery (any stage before Stage 3) | Financing | Yes, if financeable → recovery is **paused**, not deleted | A gentle reminder doesn't stop a buyer accepting on TReDS |
| Recovery Stage 3 or 4 | Financing | **No** | Once a dispute is formal, financing is unrealistic; the engine flags it as a dispute |
| Financing before AWAITING_ESIGN | Recovery | Yes → financing is cancelled | Nothing assigned yet |
| Financing AWAITING_ESIGN or later | Recovery | **No** | After signature the receivable belongs to the financier; recovery actions would be wrong and confusing |
| Financing BUYER_DECLINED / NO_BIDS / CANCELLED | Recovery | Yes, one-click "Switch to Option 2" | |

Guards are enforced in `workflow/tracks.py` **and** by the database (a unique partial index
allowing one active track per case, plus an optimistic `version` check). A race between two tabs
must produce exactly one winner and a `409` for the loser.

## 4. Financeability check (`finance/financeability.py`, pure)

Inputs: the engine output plus case facts. **Not** financeable if any of these is true:

- the engine gate failed (not micro/small, trader, Udyam after supply);
- a written objection or dispute is recorded;
- recovery is at Stage 3 or later;
- the amount is below `financing.min_amount`;
- the buyer is flagged as not on TReDS **and** the user declines to invite it;
- the due date has passed by more than `financing.max_overdue_days`
  (config, default `0` = only before the due date; OQ-11).

Reasons come back as codes with plain-English messages, exactly like the engine's warnings —
never as a silent `false`. Option 2 stays available whenever Option 1 does not.

**Never recommend one option** (golden rule 20): the comparison returns both with numbers and
`recommendation: null`.
