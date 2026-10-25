# AGENTS.md: standing instructions for every AI agent in this repo

Copy this file to the repo root as `AGENTS.md` (and `CLAUDE.md` if your tool reads that). Read it, then `docs/architecture.md`, before touching anything.

## 1. What this project is

SamadhaanOS helps micro and small suppliers in India enforce their payment rights under the MSMED Act without wrecking the customer relationship. It checks eligibility, fixes statutory dates, computes interest, shows the buyer's cost of delay, tracks limitation, and produces a graduated escalation ladder. Hackathon: Srujana Tech Fest 2026, Legal Services track, problem LS-03.

Team: **Aniruddha** owns backend and legal rules. **Mochi** (Sanay) owns frontend and UX. Two humans, so you are an extension of one of them. Know which one before you start.

## 2. Golden rules (violating any of these is a bug)

1. **Do not invent law.** If a rule, section number, threshold, date, rate or case holding is not already in `backend/config/statute_config.json` or `docs/statute-sheet/`, do not guess it. Write the question in `docs/open-questions.md`, use the documented default, and surface it as an `assumption` or `warning`.
2. **No LLM and no network in the legal-math path.** Code under `backend/engine/` is pure, deterministic, and free of I/O and clocks.
3. **Money and rates are `Decimal`**, serialized as strings. Never floats in the legal path.
4. **Config over constants.** No statutory numbers in code. Read them from the config object passed in.
5. **The contract is frozen.** Do not rename or remove fields in `contracts/`. Additive changes only, through the protocol in `architecture.md` section 9.
6. **The frontend never computes legal numbers.** It formats what the engine returns.
7. **Every on-screen number comes from the engine.** Mock values must be visibly labelled "placeholder" until replaced by engine output.
8. **Never combine the buyer's costs into one total.** Permanent loss, deferral cost and disclosure are separate lines.
9. **Never fabricate official documents.** No fake MSEFC forms, no fake notices that look issued by an authority. Drafts are labelled drafts.
10. **Nothing auto-sends.** The product produces drafts for the owner to approve.
11. **Synthetic data only.** No real names, Udyam numbers, GSTINs, phone numbers or secrets in the repo.
12. **Do not use v2's hand-typed worked example as an oracle.** It mixes rates across a period when the Bank Rate changed. See `architecture.md` section 12.
13. **Public claims must be true.** The organizers treat fabricated claims as grounds for disqualification. README, UI copy and the video may only claim what the repo demonstrably does. Register each claim in `docs/claims-register.md` with its evidence.
14. **No overclaiming words:** never "court-ready", "guaranteed", "legally barred", "100% accurate". Use "appears", "based on what you entered", "decision support, not legal advice".
15. **Built during the event, and disclosed.** Do not paste in code from earlier projects. Record every external library, API or dataset in `docs/dependencies.md` as you add it.

16. **Mocks are labelled, always.** Every mocked integration (eSign, TReDS-style bids, bank disbursement) shows a DEMO badge, sends `X-Simulation: true`, and uses `MOCK`-prefixed IDs. The app must refuse to start in production with a mock adapter.
17. **No impersonation.** No real bank, TReDS platform, UIDAI or government names, logos or page styling in mocks or demo data. Use fictional financiers ("Financier A/B/C"). Real names appear only in docs as "would integrate with".
18. **No Aadhaar data.** The demo eSign accepts a test OTP only. There is no Aadhaar number field, and none is stored or logged.
19. **No scripted deception.** Never generate messages that misstate who is sending them, invent an "institutional" or "compliance" sender, or script excuses for the supplier to tell the buyer. Messages come from the supplier.
20. **Never recommend Option 1 or Option 2.** Show both with numbers; `recommendation` stays null.
21. **Never claim the financier can enforce MSMED rights** (s.16 interest, MSEFC). It's an open question (OQ-10).

## 3. Agent roles and file boundaries

Only the listed agent edits the listed paths. If you need a change outside your boundary, write a request in `docs/worklog.md` instead of making it.

| Agent | Works for | May edit | Must not edit | Special rules |
|---|---|---|---|---|
| **Engine** | Aniruddha | `backend/engine/**`, `backend/config/**`, `backend/tests/dev/**` | `backend/tests/spec/**`, `frontend/**`, `contracts/**` (except via API agent) | Must make `tests/spec/` pass without editing it. If a spec test seems wrong, raise it in the worklog and cite the statute sheet. |
| **API and artifacts** | Aniruddha | `backend/app/**`, `backend/artifacts/**`, `backend/extraction/**`, `backend/presets/**`, `contracts/**` | `backend/engine/**` (call it, don't change it), `frontend/**` | Owns the export of `openapi.json` and generated `types.ts`. |
| **Test author** | Aniruddha (separate session) | `backend/tests/spec/**`, `docs/test-oracles.md` | everything else | **Do not open `backend/engine/**`.** Work from the statute sheet and `architecture.md` only. Use round numbers with hand-computed expected values written in comments. |
| **Frontend** | Mochi | `frontend/**` | `backend/**`, `contracts/**` | Consume generated types. Fixtures come from `contracts/fixtures/`. Use the installed frontend-design skill if available. |
| **Reviewer (red team)** | Either | `docs/review-*.md` only | all code | Read-only. Tries to break rules: wrong dates, rounding, unverified constants, fake certainty in UI copy. |
| **Workflow & integrations** | Aniruddha | `backend/workflow/**`, `backend/ports/**`, `backend/adapters/**`, `backend/store/**`, `backend/app/routes/financing.py`, `recovery.py`, `webhooks.py`, `events.py` | `backend/engine/**`, `backend/finance/**` (call, don't change), `frontend/**` | Every mutation is idempotent; every webhook is verified and deduplicated; every transition goes through the transition table. |
| **Finance maths** | Aniruddha | `backend/finance/**` | everything else | Pure functions, Decimal only, no I/O. Same rules as the legal engine. |
| **Mock providers** | Either | `mock_providers/**` | `backend/**`, `frontend/**` | Simulation only. Real signed HTTP webhooks. Deterministic, seeded outputs. Fictional names. |
| **Docs** | Either | `README.md`, `docs/**` except statute sheet | code | Writes the AI-assistance disclosure and known-limitations sections truthfully. |

## 4. Working protocol

1. **Before starting:** read `AGENTS.md`, `docs/architecture.md`, `docs/open-questions.md`, and the last 20 lines of `docs/worklog.md`. Confirm which prompt from `docs/prompts.md` you are executing.
2. **Plan briefly.** State your plan in 5 lines or fewer, then build. Do not ask the human questions that the documents already answer.
3. **Small steps, runnable at every step.** Keep `make test` and `make dev` working. Do not leave the repo broken at the end of a task.
4. **Stop and ask** only when: a rule is missing from config and the docs, two documents contradict each other, or a task would require editing outside your boundary.
5. **Finish with the worklog.** Append to `docs/worklog.md`: date and time, AI tool name, agent role, prompt id, what changed, what is unverified, and any open question raised. Five lines maximum. This is part of the AI-use disclosure.
6. **Do not refactor beyond your task.** No renames, no formatting sweeps, no dependency changes unless the prompt says so.

## 5. Conventions

**Backend (Python)**
- Python 3.11+, FastAPI, Pydantic v2, pytest. Type hints everywhere. `ruff` and `black` defaults if installed.
- Engine functions take explicit inputs and a config object and return Pydantic models or dataclasses. No globals, no hidden state.
- Month stepping uses `dateutil.relativedelta` (or an equivalent tested helper) with end-of-month clamping.
- Rounding: `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)` at each ledger row.
- Every result that depends on a rule includes a `citations[]` entry. Every default taken because of an open question adds an `assumptions[]` entry.
- Error messages are plain English a business owner could read.

**Frontend (TypeScript)**
- Next.js App Router, TypeScript strict, Tailwind, Recharts.
- Use generated types from `contracts/types.ts`. No `any` for API data.
- Money and percentages are strings from the API. Format only at the edge with `lib/format.ts`.
- All user-visible strings go through the i18n dictionary. No hard-coded copy in components.
- Every status uses icon plus text (not colour alone). Every drawer is keyboard operable.
- Persona and language live in URL params so demo states are reproducible.

**Both**
- Commit small, descriptive messages. Keep any co-author trailer your tool adds. The README discloses AI assistance.
- Never commit secrets. Use `.env` (git-ignored) and `.env.example`.
- File and folder names follow the layout in `architecture.md` section 3.

## 6. Definition of done for any task

- It runs. Tests relevant to the task pass.
- No new unverified constant is relied on silently.
- The contract is unchanged, or changed through the protocol.
- The worklog entry is written.
- A human who did not write it can explain what it does in two minutes.

## 7. Things agents get wrong here (watch for these)

- Anchoring the clock on the invoice date instead of delivery.
- Treating a non-written or late objection as pausing the clock.
- Recomputing the cap per supply date ("regimes"). There are none.
- Adding the 43B(h) tax timing effect to interest as a "total loss".
- Using one fixed Bank Rate across a delay period that spans a rate change.
- Using floats for rupees. Rounding only at the end instead of per row.
- Producing documents that read like official filings.
- Making the UI say "you will win" or "guaranteed". Use cautious, sourced language.
- Hand-typing numbers into components, slides or fixtures instead of generating them from the engine.
- Labels like "court-ready" or "legally barred" that state a legal conclusion. Gate and readiness copy must say "appears" and show the rule.
- Adding a dependency without recording it in `docs/dependencies.md`.
- Letting the mock compute bid discounts. The mock only picks rates; `backend/finance/` computes every rupee.
- Parsing a webhook body before verifying its signature over the raw bytes.
- Using floats or REAL columns for money in the database. Money is TEXT decimal strings.
- Applying an out-of-order webhook instead of parking it.

## 8. Escalation

If something seems legally wrong, do not fix it silently. Add an entry to `docs/open-questions.md` with: the rule, where it appears, what you believe is wrong, and what source would settle it. Aniruddha resolves it against the statute sheet.