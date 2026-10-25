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
