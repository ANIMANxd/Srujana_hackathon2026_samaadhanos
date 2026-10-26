# Contract and backend requests from the frontend

Written by the frontend (Mochi's side). The frontend does not edit `backend/`,
`contracts/` or the `Makefile`; this file is the handoff. Every item says what
the UI does **today** without it, so nothing here blocks the demo, and the UI
picks the real thing up automatically after a `git pull` (the
`sync-contracts` script re-copies `contracts/types.ts`, fixtures, artifact
samples and extraction samples on every `npm install`, `npm run dev` and
`npm run build`).

Status key: **open** = not done yet. **done** = shipped by the backend and used by the UI.

| ID | Request | Why the UI needs it | What the UI does now | Status |
|---|---|---|---|---|
| CR-1 | Optional guidance hints on `CaseEvaluationResponse`, e.g. `guidance: { stage, action_code, top_defense_id } \| null` (additive) | Spec F10: one action and the top defense for the current stage | Uses `evidence_readiness.recommended_stage` and picks the first `AT_RISK`, then `OPEN_QUESTION`, then any defense | open |
| CR-2 | `GRN` in `EvidenceKind`, and warning code `GRN_MISSING_DEEMED_ACCEPTANCE` (prompt B3a) | Spec C2: deemed-acceptance line whenever the GRN is missing | Shows the "s.2(b) · deemed acceptance" tag when `timeline.objection_status == DEEMED_ACCEPTANCE`, and already listens for the warning code | open |
| CR-3 | Remove `ReadinessBand.COURT_READY` now that `EVIDENCE_COMPLETE` exists (both humans must agree, architecture §9.3) | "Court-ready" is a legal-conclusion claim | `EVIDENCE_COMPLETE` added by the backend and handled. Both codes map to "Evidence looks complete based on what you entered"; neither is printed | partly done (removal open) |
| CR-4 | `POST /api/v1/extract-evidence` (B9) | Upload and review screen (F12) | Uses the generated `ExtractionResponse`: line citations, tagged WhatsApp messages, extractor notes. Accepts `.txt` only, as the backend does. Offline, the three synthetic samples show the result the extractor saved for them (`backend/extraction/cache`), labelled | done |
| CR-5 | `POST /api/v1/generate-artifact` (B8) | Send drawer (F11) | Drafts come from the backend (Stage 1 uses `STAGE1_ACCEPTANCE_NOTE` when there is no delivery proof). PDF download when `pdf_base64` is present. Offline, unedited presets show the engine-generated `contracts/fixtures/*.md` sample, labelled; other cases say drafting needs the backend. The frontend's own fallback templates were removed | done |
| CR-6 | A catch-all exception handler so unexpected 500s also use the `{error:{code,message}}` envelope | The UI treats a 5xx **without** the envelope as "backend unreachable" (the dev proxy returns that when FastAPI is down) | A real engine crash shows as offline instead of an error | open |
| CR-7 | Presets `case_02` onward (B7) | Dues list and judge console | Uses all seven backend presets. The frontend's stand-in demo cases were deleted | done |
| CR-8 | Bank-rate epochs before 2026-04-01, or preset dates inside the covered epochs | `bank_rate_on` raised `NoEpochFound` for older delays | Presets are now dated inside the configured epochs. Edited dates outside them show the engine's 400 message and keep the last good result | done |
| CR-9 | Buyer grouping by PAN (B11), or portfolio totals per buyer group | Dues summary ("total overdue across buyers") | Counts only, with a note. Adding money in the browser would be legal math (golden rule 6) | open |
| CR-10 | `POST /api/v1/simulate-settlement` | Stage 3 settlement numbers | Endpoint shipped. The Stage 3 draft from `generate-artifact` already carries the split; a dedicated simulator UI is not built yet | done (UI optional) |
| CR-12 | Makefile: wire the frontend targets now that F0 has landed. Suggested recipes (no sh syntax, per the Makefile header): `frontend:` → `npm --prefix frontend run dev`; `dev:` → start `backend` and `frontend` (two terminals is fine); `demo:` → `npm --prefix frontend run dev` after `fixtures` | F0 acceptance says `make dev` shows the shell; the Makefile is outside the frontend boundary | Run `npm run dev` inside `frontend/` (README) | open |
| CR-13 | A preset whose delay spans the configured Bank Rate change (2026-10-07), e.g. a calculation date in November 2026 | F5 acceptance: toggling rate mode on a preset should visibly change the ledger. Every current preset ends before 2026-10-07, so floating and frozen give the same figures | The Math tab works; the demo needs a judge-console edit first (calculation date past 2026-10-07). Verified on case_04 moved to 2026-11-15: floating splits 16.50% / 17.25%, frozen keeps 16.50%, total claim 3,89,056.23 vs 3,88,748.93 | open |
| CR-14 | Optional `recommended_reason` (a short plain-English sentence) on `evidence_readiness`, next to `recommended_stage` | The Escalation tab shows why a step is recommended | The frontend states the reason from the engine's documented structural rules (no delivery proof, eligibility open, evidence complete, otherwise settle), keyed in i18n. Replace it with the engine's own sentence when it exists | open |
| CR-15 | v1.2 customer-book routes. The frontend assumes these paths (please confirm or correct): `GET /customers?sort=<CustomerRow field>&dir=asc\|desc` → `{customers: CustomerRow[], groups: CustomerGroupRow[]}`; `GET /customers/{id}` → `CustomerProfile`; `GET /customers/suggestions` → `{suggestions}`; `GET /insights` → `PortfolioInsights`; `GET /cases/{id}/payments` → `{payments}`; `POST /customers/{id}/gstins {gstin}`, `POST /customers/{id}/gstins/{gstin}/detach`; `POST /customers/{target}/attach\|detach {customer_id}`; `POST /customer-groups {label, customer_ids}` → `CustomerGroupRow`; `POST /customer-groups/{gid}/members {customer_id}`, `POST /customer-groups/{gid}/members/{cid}/unlink`; `POST /customers/suggestions/dismiss\|undo-dismiss {a, b}`; (payments are shipped and used as built: `GET /cases/{id}/payments` → `PaymentListResponse`, `POST /cases/{id}/payments` → `CaseDetail`, `POST /cases/{id}/payments/{pid}/void` → `CaseDetail`); `POST /imports/preview` (multipart `file`) → `ImportPreview`; `POST /imports/{preview_id}/confirm` → `ImportResult`. All mutations take `Idempotency-Key`; none take `If-Match` | v1.2 publishes the shapes but no routes yet | `lib/api.ts` calls these paths. Offline (and until the routes exist) reads fall back to `contracts/fixtures/v5/`, labelled sample and placeholder; mutations are off. Mutations with no contract response shape are typed `void` and the screen re-reads | open |
| CR-16 | Set `group_id`/`group_label` on the members inside `customer-group-row.json` and `customer-profile.json` (they are `null` today), or confirm the group's `members` list is the source of truth | The grouped view must agree with the group | `sectionRows` uses the row's `group_id`, else the group's `members` list | open |
| CR-17 | Additive fields on `CustomerRow` (and the same on `CustomerGroupRow` as group totals): `interest_outstanding` and `daily_accrual` (per-customer sums of the engine's figures), `avg_days_to_pay` + `based_on` + `min_history`, `on_time_count` + `paid_invoice_count`, and the open cases' track states. Plus `avg_days_to_pay` as a `sort` key on `GET /customers` | Dues › Customers shows these per row: "Interest the law adds" as a live ticker, "Pays in ~N days", "On time x of n" and track chips | Each row reads `GET /customers/{id}` for stats and chips. The ticker runs only when a customer has exactly one overdue invoice (read from that case's evaluation); with several it says "On N invoices", because adding interest across invoices in the browser would be legal math. "On time" shows the server's percentage with "based on N invoices", since `on_time_count` does not exist. Group rows show no totals | open |
| CR-18 | Additive fields on `CustomerProfile` for `/customers/[id]`, matching what `backend/insights/stats.py` already computes: `series: InvoiceSeriesPoint[]` (case_id, invoice_no, accepted_on, due_date, legal_due_days, days_to_pay, days_open_so_far, days_overdue, status, outstanding, on_time, plus the final `paid_on`), `stats.on_time_count`, `stats.interest_accrued_now`. Optionally the per-invoice buyer-cost lines and the customer's audit events, so the page needs one request | Payment-history chart, "On time x of n", the interest tile, and the paid-on column | `lib/profileExtras.ts` reads these names defensively if the response has them. Without them, the chart says the server has not sent the history, On time shows the percentage, and interest uses the single overdue invoice's evaluation (or "On N invoices"). Cost lines and the timeline come from `GET /cases/{id}` and `/cases/{id}/events` per invoice. Checked against a scratch mock that sends these names | open |
| CR-11 | Spec findings F1–F7 in `docs/test-oracles.md` (e.g. F1 rest-day payment dropped, F3 Silpi date never compared) | Judge manipulations 4 and 5 show engine output as-is | Nothing to change in the UI; it shows whatever the engine returns | open (engine) |

## Review 2026-10-25 (`docs/review-2026-10-25.md`), frontend view

The review was written against the frontend before commit `2969ede`. Its three
frontend items are already fixed on `main`:

- **B1** `BAND_TONE` now has `EVIDENCE_COMPLETE`; typecheck and build pass.
- **m6** `frontend/demo-cases/` is deleted; the seven backend presets are used.
- **m7** the `tpl.*` fallback drafts are removed; drafts come from `/generate-artifact` only.

Engine findings that show up in the judge console (nothing to change in the UI, it shows the engine's answer):

- **M2 / F3** rehearsal 5 (Udyam after supply, Silpi test on the supply date) returns `ELIGIBLE`, never `BARRED_SILPI`. The pill and panel already handle `BARRED_SILPI` (lock icon, "Appears barred") and will show it once the engine compares the dates.
- **B2 / F2** an investment inside the small ceilings with class `MICRO` reads `EXCLUDED_MEDIUM`.
- **M1, M3, M4** payment on rest day = calculation day, duplicate payments, negative credit days: the console accepts these inputs and shows whatever the engine returns. It already refuses negative credit days (whole numbers only).

## Notes for running together

- No CORS change is needed. The frontend proxies `/api/v1/*` to `BACKEND_URL`
  (default `http://127.0.0.1:8000`; see `next.config.ts`).
- Fixtures come from `contracts/fixtures/` and are never edited on the frontend.
  Regenerate them with `make fixtures` on the backend side.
- The top bar shows **Engine live** or **Offline** from `GET /health`; while offline a persistent "Offline demo data" banner sits under it.
