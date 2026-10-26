# SamadhaanOS

**Enforce without enmity.** A micro or small supplier in India is owed money by a
larger buyer. The law is on the supplier's side and prices the delay every day,
but the supplier cannot afford a lawyer, cannot prove the delivery, and cannot
afford to lose the customer. SamadhaanOS turns that into a clock, a number, a
record and a graduated ask.

Srujana Tech Fest 2026 · Legal Services track · problem LS-03.

Status: **working prototype.** The engine, API, contract, frontend and document
drafts run end to end. Eight independent spec tests are red by design and are
listed under [Known limitations](#known-limitations).

---

## What it actually does

One journey, and it works today:

1. **Pick a case** (or upload an invoice and confirm the extracted fields against
   their source line — nothing reaches the engine until a human approves it).
2. **The eligibility gate answers first.** If the Act does not help this supplier
   — medium enterprise, trader, or registered after the relevant date — the app
   says so, explains why, points at the civil route, and shows no number. It does
   not produce a confident zero.
3. **The clock is fixed from delivery, not the invoice.** A "Net 90" purchase
   order is clamped to the statutory 45 days, and the clamp is shown rather than
   hidden. If the buyer never gave a Goods Received Note and never objected in
   writing, acceptance is deemed and the clock still runs.
4. **The interest ledger is computed** at three times the RBI Bank Rate,
   compounded monthly, split at every Bank Rate change, with each row rounded to
   the paisa and cited to the section it came from.
5. **The buyer's cost of delay is shown as three separate lines** — permanent
   loss, the 43B(h) deduction timing, and the s.22 disclosure duty. They are
   never added together, because adding a loss, a cash-timing effect and a
   disclosure duty produces a number that would not survive a hearing.
6. **The escalation ladder drafts the next move** — an acceptance note, a memo
   for the buyer's finance team, a settlement term sheet, and an evidence pack
   for the MSME ODR portal. Every stage is a draft the owner approves.
7. **The owner sends it themselves** — a WhatsApp link and a `mailto:` link with
   the draft prefilled. The app never sends on its own; it hands the approved
   text to the owner's own app. Automated dispatch is deliberately out of scope.

The reasoning behind each rule, and the traps this project deliberately avoids,
are in [`architecture.md`](architecture.md) and [`docs/test-oracles.md`](docs/test-oracles.md).

---

## How to run

Requires Python 3.11+ and Node 20+.

```bash
pip install -r requirements.txt

# terminal 1 — API on :8000
make backend

# terminal 2 — app on :3000
cd frontend && npm install && npm run dev
```

Then open <http://localhost:3000>. The app works with the backend down too: preset
cases fall back to engine-generated fixtures and the top bar says **Offline**.

```bash
make test                    # backend suite
npm run typecheck && npm run lint && npm run smoke   # frontend, from frontend/
```

The offline demo sequence is in [`frontend/DEMO.md`](frontend/DEMO.md).

---

## Sample documents

[`sample_data/`](sample_data/README.md) holds a synthetic document corpus a judge
can open: PDFs of a GST invoice, purchase order, delivery challan, goods receipt
note, Udyam data extract, GST return extracts, a written objection and a
remittance advice, plus WhatsApp exports and a degraded/photo OCR stress set.
Every page is watermarked SPECIMEN, every party and GSTIN is fictional, and the
Udyam page is a labelled data extract rather than a certificate.
`sample_data/MANIFEST.json` is the OCR ground truth; rebuild the corpus with
`python sample_data/generate_samples.py` and check it with
`python sample_data/verify_samples.py`.

---

## Sending is manual, on purpose

The app drafts; the owner sends. A stage produces a `wa.me` link and a `mailto:`
link with the text prefilled, and nothing leaves the app until the owner presses
send in their own WhatsApp or mail client. That keeps the relationship decision
with the person who owns the relationship, and it means the prototype never
holds a supplier's messaging credentials.

Server-side dispatch is a deliberate next step, not a missing feature: it needs
provider accounts, a verified business number, and an audit trail before it is
safe to ship.

---

## Architecture in one paragraph

The legal core is a pure, stateless Python function: no clock, no network, no
randomness, `Decimal` money, and every statutory constant read from a versioned
JSON config with a citation. The probabilistic work — reading an invoice or a
WhatsApp export — lives outside that core and stops at a human confirmation
gate. The API is FastAPI with a frozen contract (`contracts/`), the frontend is
Next.js reading generated types, and the frontend computes no legal number: it
formats what the engine returned.

```
evidence → [extraction + human confirm] → [statute config + engine]
        → [timeline, ledger, buyer cost, limitation, defences, readiness]
        → [escalation ladder → approved draft → owner's own WhatsApp or email]
```

---

## What is deliberately not claimed

- **Not legal advice, and not a filing.** Drafts are marked `# DRAFT`, never
  resemble a government form, and filing stays on the official portal.
- **No fabricated certainty.** A blocked case shows no amount. Missing delivery
  proof caps the evidence score and blocks escalation instead of guessing.
- **No statute constant is presented as verified yet.** Every constant in
  `backend/config/statute_config.json` is flagged `verified: false` until it is
  captured from a primary source in `docs/statute-sheet/`, and the engine
  surfaces `UNVERIFIED_CONSTANT` for each one a calculation relies on. That flag
  is visible on screen. It is the honest state, not a finished one.

---

## Known limitations

1. **Eight red tests.** Seven spec findings (a payment on a rest day that is also
   the calculation date, enterprise class taken from the stated class, the Silpi
   chronology check never comparing dates, duplicate payments, a negative credit
   period, a calculation date before delivery answered 200, and the order of
   `late_complaints`) plus one contract test for the Silpi edge. They are
   recorded in [`docs/test-oracles.md`](docs/test-oracles.md) and
   [`docs/review-2026-10-25.md`](docs/review-2026-10-25.md); none is hidden.
2. **No primary-source statute captures yet.** `docs/statute-sheet/CHECKLIST.md`
   lists V1–V11, all `captured: no`. Until they land, the money surface is
   provisional by construction.
3. **Interpretive areas are surfaced, not resolved** — whether a PO counts as a
   written agreement, the Silpi anchor date, and the interest appropriation
   order. Each appears as an assumption on screen.
4. **Extraction is regex-first.** Ambiguous dates are read DD/MM/YYYY and the
   ambiguity is flagged rather than resolved. Every field needs confirmation.
5. **Sending is manual.** The app produces a `wa.me` link and a `mailto:` link;
   the owner presses send in their own app. There is no server-side dispatch, no
   delivery receipt and no scheduling.
6. **Kannada covers the owner-facing MVP cards only** and awaits a native
   speaker's review.
7. **Not covered:** medium-enterprise suppliers, traders, actual filing, legal
   representation.
8. **GSTIN validation is format only.** The 15-character pattern is checked; the
   check digit is not verified and no GST portal lookup is made. A GSTIN that
   fails the pattern becomes a provisional customer with a warning; it is never
   silently dropped or treated as a legal identity.

---

## Built with AI assistance

The project was built during the event with AI coding agents under written
prompts, with a human making every legal and product decision. The legal-math
path contains no LLM call and no network access. Both team members can explain
the code, the design decisions and the outputs. Details and the claims register
live in `docs/`.

Full design: [`architecture.md`](architecture.md). Agent rules:
[`AGENTS.md`](AGENTS.md). Prompt history: [`docs/worklog.md`](docs/worklog.md).
