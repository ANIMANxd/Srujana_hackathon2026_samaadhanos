# Frontend v4 review (F1 to F8)

Written 2026-10-25. Role: Reviewer, read-only. No code was changed; this file is the only write.

## Sources, and what was missing

- `docs/prompts_v4.md` and `docs/frontend-structure.md` **do not exist** in the repo. F1 to F8 below are the eight prompts as they were given in the working session (persistent cases, choice card, early stepper, e-sign modal, recovery wiring, Dues from `/cases`, judge console, audit). Section 7 of the frontend structure doc could not be read; the copy and layout rules were taken from `architecture_v4_two_options.md` section 10.
- Read: `AGENTS.md`, `architecture_v4_two_options.md` sections 1, 5, 9, 10, `state-machines.md`, and the **real backend routes** (`backend/app/routes/*.py`, `main.py`, `schemas_v4.py`), because the frontend was built before most of them existed and against a stand-in server.

## Checks run

| Check | Result |
|---|---|
| `npx tsc --noEmit` | exit 0, no errors |
| `npm run lint` | clean |
| `npm run i18n:check` | ok: 873 English keys, no blank fallbacks |
| `npm run build` | compiles; `/case/[id]/early` is in the route table |
| `npm run smoke` | all 37 routes ok, demo and language checks ok (backend offline) |
| Frontend unit tests | **none exist** (no test runner, no `tests/` folder). `smoke` and `i18n:check` are the only automated checks. |
| `any` on API data | none: grep for `: any`, `as any`, `<any>`, `any[]` in `lib components app` finds only a comment |
| Banned words | `instant cash`, `guarantee`, `bad cop`, `shield`, `institutional ledger`, `court-ready` are absent from code and copy (two code comments say "never guaranteed") |
| Real bank or platform names | none of RXIL, M1xchange, Invoicemart, banks, UIDAI, DigiLocker. "TReDS" (the RBI scheme, not a platform) appears in 4 copy strings, as the spec's own wording does |
| Hard-coded user-facing text in v4 components | none found; the only literals are the command `make db-reset` and the "—" glyph |

**Important:** everything marked PASS below was exercised in a browser against a **stand-in server I wrote**, not the real backend. Section "Real backend mismatches" lists where the real routes differ from what the frontend assumed. Several PASS rows are therefore PASS for the UI and PARTIAL for the integration, and are marked PARTIAL.

## Table

| Prompt | Requirement | Status | Evidence or what's missing |
|---|---|---|---|
| F1 | Typed calls for every v1.1 endpoint in `lib/api.ts` | PARTIAL | Present: `createCase`, `listCases`, `getCase`, `getOptions`, `startFinancing`, `requestBuyerAcceptance`, `listBids`, `selectBid`, `cancelFinancing`, `startRecovery`, `markRecoverySent`, `getEvents`, `verifyEvents`, `streamUrl`, `setMockScenario`, `setMockClock`. Webhooks deliberately have no client. Missing: `POST /recovery/odr-filed` (exists in the backend). Wrong: mutations are typed as returning `CaseDetail`/`ESignSession`, but the backend answers `FinancingActionResponse` / `RecoveryActionResponse` (types exist in `contracts/types.ts`); `listBids` is typed `Bid[]` but the backend returns a `FinancingActionResponse` with a `bids` field |
| F1 | `lib/idempotency.ts`: new key per user action, reused on retry of the same action | PASS | `idempotencyKeyFor` / `releaseIdempotencyKey` |
| F1 | `lib/useTrack.ts`: `GET /cases/{id}`, SSE `/stream`, 3 s polling fallback, exposes `{caseDetail, track, version, refresh}` | PASS | `useTrack`; `EventSource(streamUrl)`, `POLL_MS = 3000`, plus a 10 s safety poll while the stream is open. The real stream sends unnamed `data:` JSON, which `onmessage` handles |
| F1 | `IdempotentButton`: disables on click, sends `Idempotency-Key` and `If-Match: version` | PARTIAL | `components/common/IdempotentButton.tsx` disables (state plus a ref against double clicks) and sends both. **Defect:** `If-Match` is omitted when `version` is null. The real backend answers 400 to a missing `If-Match` and expects `If-Match: 0` when no track exists yet (`_require_if_match`, `financing.py`), so "Check if this invoice can be financed" and the first "Prepare this step" fail against the real server |
| F1 | On 409: refresh and show "This changed in another tab. Refreshed." | PASS | `IdempotentButton` 409 branch calls `onConflict()`; copy is `action.conflict` |
| F1 | Upload Approve → `POST /cases` → `/case/[id]` | PASS | `UploadScreen.approve` calls `createCase` and routes to `/case/<server id>`. Real `POST /cases` accepts the same body and replaces `case_id` |
| F1 | `/case/[id]` loads by id | PASS | `useEvaluation` server mode, `useTrack`; stored evaluation shown unless edited |
| F1 | `?legacy=1` keeps the stateless path | PASS | `useEvaluation` (`legacy` forces local mode); `UploadScreen` also falls back to it when `/cases` is missing or unreachable. The flag is dropped on navigation to sub-pages (pack, send), which still work because the case is then saved locally |
| F1 | Offline: fixtures from `contracts/fixtures/v4`, banner, mutations disabled with an explanation | PARTIAL | `lib/fixturesV4.ts`, `scripts/sync-contracts.mjs`, `TrackStrip` banner, `IdempotentButton offline`. Gap: Upload Approve offline saves a local-only case instead of being disabled |
| F1 | Strict TS, no `any`, all copy in `en.ts` | PASS | see Checks |
| F2 | `ChoiceCard`, `OptionColumn`, `UnavailableReason` directly under `GuidanceCard` | PASS | `components/options/*`, placed in `CaseScreen` right after `GuidanceCard`, stored cases only |
| F2 | Fed by `GET /cases/{id}/options` | PASS | `lib/useOptions.ts` → `getOptions`; the real route exists (`routes/options.py`) |
| F2 | Debounced expected-payment-date picker on the Recover column | PASS | `ChoiceCard` date input, `useOptions` 400 ms debounce, previous answer kept while loading |
| F2 | DemoBadge on Get paid early | PASS | `components/options/DemoBadge.tsx` in the early column header |
| F2 | Unavailable option greyed out, one-line reason, link to the other option | PASS | `UnavailableReason`, `OptionColumn dimmed` |
| F2 | Active track: "In progress" + "Continue", other option locked or paused per `available_actions` | PASS | `sides()` in `ChoiceCard`. `switch_to_financing` is a guessed action code (`backend/workflow/transitions.py` lists no action for recovery states, so Option 1 never shows "Paused" there, only "Locked") |
| F2 | No "best" or "recommended" badge anywhere | PASS | grep clean; the ladder's "Recommended" was renamed "Next step" |
| F3 | Route `/case/[id]/early` | PASS | `app/case/[id]/early/page.tsx` |
| F3 | Stepper driven only by `track.state`, never advances itself | PASS | `lib/earlyFlow.ts` `earlyView`; `EarlyScreen` |
| F3 | Six steps Check, Ask, Bid, Sign, Money, Done | PASS | `EARLY_STEPS` |
| F3 | Buyer message draft, editable, WhatsApp / email / copy via `SendButtons`, "Request acceptance", live status | PASS | `components/early/AskBuyer.tsx`, `components/send/SendButtons.tsx` (extracted from `SendPanel`) |
| F3 | Bids sorted by net amount descending, valid-until countdown | PARTIAL | `BidList` sorts via `toPaise`; `BidCard` + `lib/useNow.ts`. **Defect against the real backend:** `listBids` expects `Bid[]` but the route returns `{detail, track, bids, ...}`, so the step would fail to render. Also the selected bid is looked up by `status === "SELECTED"` in a list the real route only returns while bidding is open |
| F3 | Selecting calls `POST /financing/bids/{id}/select` | PASS | `BidList` → `selectBid`. The `If-Match` version is sent (track exists) |
| F3 | Terminal BUYER_DECLINED, NO_BIDS, CANCELLED offer "Switch to Option 2" | PASS | `EarlyScreen` failure panel; NOT_FINANCEABLE also; not shown for DISBURSEMENT_FAILED |
| F3 | DemoBadge on every step | PASS | each step `li` carries `DemoBadge` |
| F3 | MOCK ids visible | PASS | bid id (`BidCard`), session id (`ESignModal`), payout ref and UTR (`SettlementStatus`), as the server sends them |
| F3 | LockedNotice after disbursal; payout shown | PARTIAL | `LockedNotice` and `SettlementStatus` render in the Done step. The payout comes from `GET /financing/payout`, which **does not exist** in the backend, so offline fixtures aside, the UTR cannot show |
| F4 | `ESignModal` with DEMO banner, document summary (parties, invoice, amount, selected bid, you receive), TEMPLATE PDF link | PARTIAL | `components/early/ESignModal.tsx` has all of it. The template link points at `/financing/esign/template.pdf`, which does not exist; the real select response returns a `consent_document` that the UI ignores |
| F4 | One 6-digit OTP input, submit posts to the API | PARTIAL | `OTP_LENGTH = 6`, `submitEsignOtp`. The route `/financing/esign/otp` **does not exist** in the backend; there is no frontend-callable OTP route at all |
| F4 | Attempts left | PARTIAL | Shown only when the server sends `attempts_left` (no such field exists today); otherwise "Only a few attempts are allowed" |
| F4 | Expiry countdown | PASS | `timeLeft(session.expires_at)`, but the session itself comes from `GET /financing/esign`, which does not exist; the real session arrives only in the select response and is not kept after a reload |
| F4 | Focus trap, Escape closes, focus returns to opener | PASS | built on `Drawer`; a browser run kept focus inside after 30 Tab presses and closed on Escape |
| F4 | Errors announced | PASS | `role="alert"` paragraph with an icon |
| F4 | No Aadhaar field, no UIDAI, government or provider styling | PASS | one input only; banner text says none is collected |
| F4 | Success closes the modal and the stepper waits for the server | PASS | `onSigned` closes, "Signed. Waiting for the server to confirm" shows in the Sign step |
| F5 | Ladder "Prepare" → `POST /cases/{id}/recovery {stage}` | PARTIAL | `components/send/RecoveryActions.tsx` → `startRecovery`. Same `If-Match: 0` defect when there is no track. Stage 4 has no Prepare |
| F5 | "I've sent it" after WhatsApp / email / copy → `POST /recovery/mark-sent` | PASS | `RecoveryActions` (shown only when used and the track is at `STAGE_n_PREPARED`) |
| F5 | Prepared / sent states from the server | PASS | `lib/recoveryFlow.ts`, `RecoveryBadge` in `EscalationLadder` and `EscalationTab` |
| F5 | LockedNotice instead of ladder actions at AWAITING_ESIGN or later | PASS | `financingLocksRecovery`; ladder, escalation tab and `SendPanel` |
| F5 | Nothing sent by the app; draft content unchanged | PASS | only record-keeping calls; `SendPanel` text path untouched |
| F6 | Dues home fed from `GET /cases` | PASS | `lib/useCases.ts`, `components/dues/CaseRow.tsx`, `DuesScreen`. Sample rows stay below |
| F6 | Row shows amount, days overdue or "due in N days" | PASS | `CaseRow`; "due in" uses `daysBetween` (date arithmetic in the browser) |
| F6 | Track chip per state ("Get paid early · Waiting for buyer", "· Bids ready", "· Money received", "Recover · Step 2 sent", "Choose an option") | PASS | `lib/dueChip.ts` `trackChip`, all financing and recovery states |
| F6 | "Paid early (simulated)" in the summary strip next to overdue and interest | PARTIAL | The card exists, but it is a browser-side sum of `accepted_amount` (BigInt paise), not a server figure. There is no "interest" stat in the strip to sit beside |
| F6 | Keep `BuyerGroupRow` working | MISSING | no `BuyerGroupRow` exists anywhere in the repo, only `BuyerRow` (kept, unchanged in behaviour) |
| F6 | Re-fetch on focus and after SSE events on the open case | PASS | `useCases` (focus, visibility, 5 s backstop, `BroadcastChannel` from `useTrack`). The cross-tab update took about 9 s in a two-tab run |
| F7 | Hidden by default (Ctrl+J or `?judge=1`) | PARTIAL | Ctrl+J and `?judge=1` work, but the top bar shows a visible "Judge console" button in normal mode (`AppShell`); it is hidden only in demo mode |
| F7 | Scenario picker for the current case | PARTIAL | `JudgeDemoControls`, 13 scenarios. `POST /mock/scenarios` **does not exist** in the backend (`mock_providers` is also absent), so Apply fails with a plain error |
| F7 | Advance clock by N days, reset clock | PARTIAL | Advance matches the real route (`POST /mock/clock {advance_days}`); it needs the API started with `MOCK_CLOCK=1`. **Reset is wrong:** the real route is `POST /mock/clock/reset`, the UI posts `{reset: true}` to `/mock/clock` and would get a 422 |
| F7 | Verify audit chain, show ok or broken seq | PASS | `verifyEvents` against the real `/events/verify` |
| F7 | Reset demo | PASS | instructions (`make db-reset`); no endpoint exists |
| F7 | Live delivery log with accepted / duplicate / rejected badges | PARTIAL | `DeliveryLog` and badges render; `GET /mock/deliveries` **does not exist**, so against the real backend it shows "not available" |
| F7 | Absent when `/health` reports production | PARTIAL | `useProductionMode` hides the console, but `/health` does not return `app_env` (the backend reports `provider_mode` and mock reachability only), so the console would not hide on `APP_ENV=production`. The real mock routes themselves 404 in production |
| F8 | Banned words absent | PASS | see Checks |
| F8 | Every status icon plus text | PASS | `StatusIcon` everywhere; a scripted pass found no colour-only status. Error text lines elsewhere (`IdempotentButton` notices) are text without an icon |
| F8 | All copy in `lib/i18n/en.ts` | PASS | no hard-coded user-facing strings found in v4 components; v4 keys have no Kannada translation (falls back to English) |
| F8 | No financing or legal maths in the frontend | PARTIAL | No rates, discounts or interest are computed. But the frontend still does arithmetic on money and dates: the Dues paid-early sum (`DuesScreen`), the pre-existing `LiveInterestTicker`, and `daysBetween` for "due in N days"; `BidList` only compares amounts |
| F8 | Indian number formatting via `lib/format.ts` | PASS | every rupee amount goes through `money()`, `moneyParts()` or `paiseToMoney()`; a scripted scan of 12 pages found no ungrouped amount |
| F8 | `docs/ux-notes.md` exists | PASS | "v4 audit" section added |
| F8 | Contrast AA, focus visible | PASS | scripted: 0 contrast failures over about 60 to 117 text nodes per page, no focus stop without a ring. Light mode only |

## Real backend mismatches (found by reading `backend/app/routes`)

1. `POST /cases/{id}/financing`, `/recovery` and the other mutations **require `If-Match`** and answer 400 without it; use `If-Match: 0` when no track exists. The frontend omits it when there is no track.
2. Every financing and recovery mutation, and `GET /financing/bids`, returns a wrapper (`FinancingActionResponse`, `RecoveryActionResponse`) with `detail`, `track`, `bids`, `esign_session`, `consent_document`. The frontend treats them as `CaseDetail`, `Bid[]`, `ESignSession`.
3. There is **no route** for: the signing session read, the OTP submit, the TEMPLATE PDF, the payout read, `POST /mock/scenarios`, `GET /mock/deliveries`. Webhooks are the only way the real flow gets from AWAITING_ESIGN onward, and the mock providers that would send them do not exist yet.
4. Clock reset is `POST /mock/clock/reset`.
5. `/health` has no `app_env`.

## Fix list, ordered by what a judge sees first

1. **F1/F5 `If-Match: 0` when there is no track.** The first click on "Check if this invoice can be financed" or "Prepare this step" fails against the real server. Frontend only.
2. **F3/F1 `listBids` and the mutation response types.** Read `bids` from the wrapper and type mutations as `FinancingActionResponse` / `RecoveryActionResponse`; use the select response's `esign_session` and `consent_document`. The Choose-a-bid step breaks without this. Frontend only.
3. **F4/F3 e-sign and payout wiring.** The session, OTP, template and payout have no real routes. Needs a backend or contract decision; record it in `docs/open-questions.md`, keep the UI as is.
4. **F7 clock reset path.** Post to `/mock/clock/reset`; show the "start with MOCK_CLOCK=1" hint on the 400. Frontend only.
5. **F7 hidden by default.** Hide the top-bar button unless `?judge=1` (Ctrl+J still opens it). Frontend only.
6. **F7 scenarios, deliveries and the production flag.** Need backend routes and `app_env` in `/health`; open-questions entries. Meanwhile make Apply and the log fail gracefully with one calm line.
7. **F6 paid-early total and `BuyerGroupRow`.** Ask the backend for the total (and a buyer name and interest figure in `CaseSummary`); note that `BuyerGroupRow` never existed.
8. **F1 Upload Approve offline.** Disable it with an explanation instead of silently saving locally, or make the local fallback explicit.
9. **F8 Kannada for v4 copy and a frontend unit test for `earlyView`, `trackChip`, `recoveryStatus`.** Lower impact; there is no test runner yet.
