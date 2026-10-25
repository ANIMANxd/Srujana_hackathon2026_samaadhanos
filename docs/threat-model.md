# Threat model (v4)

Concise extract of `docs/architecture_v4_two_options.md` section 8 ("Threat model", plus the
hardening controls it depends on). This is a hackathon-scale threat model for a demo product:
it names what is defended, what is deliberately only simulated, and what would be required
before production.

| Threat | Control | Where |
|---|---|---|
| Forged webhook | HMAC-SHA256 over `timestamp + "." + raw_body`, constant-time compare | `app/security.py`, `docs/webhooks.md` |
| Replayed webhook | `webhook_inbox` dedupe on `provider_event_id` + 300 s timestamp tolerance | `store/webhook_inbox.py` |
| Double submit (double charge / double select) | Required `Idempotency-Key` on every mutating POST under `/financing` and `/recovery`; same key + different body hash → `409` | `store/idempotency.py` |
| Race between two tabs | Optimistic `version` check (`If-Match`) + unique partial index (one active track per case) | `workflow/tracks.py`, `store/models.py` |
| Mocks reaching production | Startup guard: `APP_ENV=production` with any mock adapter → the app **refuses to start** | `app/deps.py` |
| Tampered audit trail | Append-only, hash-chained `events` (`sha256(prev_hash \|\| canonical_json(...))`); `/events/verify` reports the first broken link | `store/audit.py` |
| Malicious upload | PDF magic-byte check (not extension), 10 MB max, 20 pages max, processed in a temp dir then deleted | extraction route |
| PII leakage | No Aadhaar data ever (the field does not exist); contact phone/email stored only when needed and masked in logs | throughout |
| Abuse of demo powers | Scenario injection and clock control only when `APP_ENV != production`; OTP capped at 3 attempts per session; in-memory token bucket on mutation routes | `app/security.py` |
| Misrepresentation | `X-Simulation: true`, DEMO badge on every Option 1 screen, `MOCK`-prefixed identifiers, fictional financier aliases, no real bank/UIDAI/TReDS branding | UI + adapters |

## Honest limits (state these, do not paper over)

- The audit trail is **tamper-evident, not tamper-proof**. Say it that way in the pitch.
- Live adapters are **stubs that raise `NotImplementedError`**. Nothing here is integrated with a
  real eSign provider, TReDS platform or bank; the docs may only say "would integrate with".
- Auth is a **stub**. There is no user model, no session store and no authorisation beyond the
  `APP_ENV` guard; single-operator demo only.
- The DPDP Act is named as a **production requirement** in the README, not satisfied here.
- No Aadhaar number is collected, stored or logged, not even a fake one. The demo eSign accepts a
  test OTP only.
- Never claim a financier can enforce MSMED rights (OQ-10). The demo asserts the opposite: the
  financier is not the "supplier" under the Act.
