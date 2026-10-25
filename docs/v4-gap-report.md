# v4 two-option model: gap report

Written 2026-10-25 15:41 IST. Role: Reviewer (read-only). No code, config or contract changed.

**Prompt id:** `v4-gap-report` (given in-session; `docs/prompts.md` does not exist, as every
earlier worklog entry also records).

## 0. Blocker: the spec this report was meant to measure against is absent

| Expected | Actual |
|---|---|
| `docs/architecture_v4_two_options.md` | **does not exist** anywhere in the repo |
| `docs/prompts.md` | does not exist |
| `docs/architecture.md` | exists as `architecture.md` at the repo **root**, not under `docs/` |
| `docs/v4-gap-report.md` | did not exist (this file) |

The v4 component list in this report therefore comes from the two places that *do* describe
v4: the task prompt itself, and `AGENTS.md` section 3, whose role table already names the
intended v4 paths (`backend/workflow/**`, `backend/ports/**`, `backend/adapters/**`,
`backend/store/**`, `backend/finance/**`, `backend/app/routes/{financing,recovery,webhooks,events}.py`,
`mock_providers/**`) plus golden rules 16-21 (DEMO labelling, no impersonation, no Aadhaar,
no scripted deception, never recommend an option, never claim a financier can enforce
MSMED rights).

Consequence: every "PARTIAL" or "MISSING" verdict below is against **AGENTS.md + the prompt**,
not against a written v4 design. Where the design would decide a shape (option fields,
transition names, SSE event names, store schema), this report says so instead of guessing.
See OQ raised at the end.

## 0.1 Baseline green-ness (measured, not assumed)

`python -m pytest backend/tests -q` → **558 passed, 8 failed, 22.71s**

| Failure | Owner |
|---|---|
| `contract/test_judge_manipulations.py::test_judge_5_flip_the_udyam_date_past_the_silpi_test_date` | F3, `docs/test-oracles.md` |
| `spec/test_invariants.py::test_shuffling_objections_does_not_change_the_output` | F7 |
| `spec/test_malformed_inputs.py::test_calculation_date_before_delivery_is_refused` | F6 |
| `spec/test_malformed_inputs.py::test_duplicate_payments_are_refused` | F4 |
| `spec/test_malformed_inputs.py::test_other_impossible_values_are_refused[written_credit_days--20-negative credit days]` | F5 |
| `spec/test_s3_interest_ledger.py::test_payment_on_the_rest_day_that_is_also_the_calculation_day` | F1 |
| `spec/test_s4_gate_blocks.py::test_a_supplier_inside_the_ceiling_is_not_excluded_as_medium` | F2 |
| `spec/test_s4_gate_blocks.py::test_silpi_block_when_the_udyam_date_falls_after_the_test_date` | F3 |

**`make test` is red before v4 starts.** The standing instruction "keep `make test` green at
every step" cannot be satisfied by v4 work alone; it needs F1-F7 resolved by the engine owner
or an explicit decision to treat the spec suite as a known-red canary. This is the single most
important fact for planning v4.

`make dev` starts the **backend only** and prints `--- frontend: not yet implemented until F0 ---`
(`Makefile:11-19`), although the frontend ships. `make frontend` prints the same. That is
CR-12, still open.

Section 2's verdicts are about *presence*, not about whether the baseline is green.

## 1. What exists

### 1.1 Engine (`backend/engine/`, FROZEN — call only)

| Module | Public surface worth calling |
|---|---|
| `evaluate.py` | `evaluate_case(config: StatuteConfig, request: CaseEvaluationRequest) -> CaseEvaluationResponse` (:178) |
| `config.py` | `StatuteConfig` (:177), `ConfigEntry`, `BankRateEpoch`, `SizeEpoch`, `SizeLimits`, `TaxPreset`, `Warning`, `ConfigError`/`NoEpochFound`/`StrictVerificationError` |
| `gate.py` | eligibility gate, `INELIGIBLE_STATUSES` |
| `acceptance.py` | due-date / deemed-acceptance rules |
| `interest.py` | s.16 ledger, `bank_rate_on`, rest days |
| `buyer_cost.py` | three separate cost lines, never summed |
| `limitation.py` | limitation clock |
| `defenses.py`, `readiness.py` | defenses, `recommended_stage` |
| `settlement.py` | `evaluate_settlement(...)` - the only existing "two-way" maths |
| `money.py`, `dates.py`, `text.py`, `env.py` | Decimal helpers, month stepping, `strict_verified_enabled()` |

Rules already honoured and worth not breaking: no I/O, no clock, no network, no LLM, Decimal only.

### 1.2 API (`backend/app/`)

**One file holds every route: `backend/app/main.py`.** There is no `backend/app/routes/`
package yet, although `AGENTS.md:47` assigns v4 routes to `backend/app/routes/financing.py`,
`recovery.py`, `webhooks.py`, `events.py`. Creating that package is v4 work.

| Route | Line | Function |
|---|---|---|
| `GET /api/v1/health` | :87 | `health()` |
| `GET /api/v1/config` | :98 | `get_config()` |
| `GET /api/v1/presets` | :108 | `list_presets()` |
| `GET /api/v1/presets/{preset_id}` | :118 | `get_preset()` |
| `POST /api/v1/evaluate-case` | :160 | `evaluate_case()` |
| `POST /api/v1/simulate-settlement` | :166 | `simulate_settlement()` |
| `POST /api/v1/generate-artifact` | :197 | `generate_artifact()` |
| `POST /api/v1/extract-evidence` | :233 | `extract_evidence()` (multipart `file`) |

Support: `_run_engine()` (:146), `_statute_config()` (:131), `_error()` (:54) producing the
`{error:{code,message}}` envelope, `validation_error_handler` (:60), `http_exception_handler` (:74),
`schemas.py` (all Pydantic models), `config_loader.py` (`load_config` :44, `objection_window` :63),
`export_openapi.py`, `export_types.py`, `export_fixtures.py`.

### 1.3 Artifacts (`backend/artifacts/`)

`kinds.py` → `ArtifactKind` (5 members), `STAGE_BY_KIND`, `KIND_TITLES`.
`generate.py` → `build_artifact(...)` (:53), `ArtifactResult` (:42).
`availability.py` → `availability(...)` (:43), `_gate_reasons` (:121), `_money_absent_reason` (:141),
`_stage4_block_reasons` (:166).
`stage1.py`, `stage2.py`, `stage3.py`, `stage4.py` (templates), `common.py` (`inr`, `pct`,
`draft_banner`, `closing_footer`, `assumptions_section`, `md_table`), `pdf.py` (reportlab),
`portal_fields.py` (V10 loader), `unavailable.py`.

### 1.4 Extraction (`backend/extraction/`)

`extract.py` (entry), `fields.py`, `text.py`, `tags.py` (the five chat tags), `whatsapp.py`,
`confirm.py` (`ConfirmSpec` :19 - maps a candidate onto a real `CaseEvaluationRequest` path),
`llm.py` (opt-in behind `EXTRACTION_LLM` + `EXTRACTION_LLM_URL`, default off), `cache.py`,
`cache_build.py`, `cache/*.json` (3), `demo/*.txt` (3).

### 1.5 Presets (`backend/presets/`)

`case_01`, `case_02`, `case_03`, `case_04`, `case_05a`, `case_05b`, `case_06` - 7 files, input
only, each `{title, note, why_calculation_date?, request}`. No outputs stored (golden rule 7).

### 1.6 Contracts (`contracts/`)

`openapi.json` - 8 paths, 67 component schemas. `types.ts` - generated mirror.
`fixtures/` - 7 `*.request.json`, 7 `*.response.json`, 5 `case_01.STAGE*.md` artifact samples.
Contract version pinned at `1.0`; changes are additive per `architecture.md` section 9.
Note `contracts/types.ts:201 webhooks: Record<string, never>` is only the OpenAPI components
stanza - **there is no webhook route**; do not read it as one.

### 1.7 Tests (`backend/tests/`)

- `contract/` - `test_contract.py`, `test_artifacts.py`, `test_extraction.py`,
  `test_fixtures_export.py`, `test_judge_manipulations.py`, `test_openapi_conformance.py`,
  `conftest.py`, `snapshots/` (15 `.txt`).
- `spec/` - `helpers.py`, `conftest.py`, `test_s2_acceptance_dates.py`,
  `test_s3_interest_ledger.py`, `test_s4_gate_blocks.py`, `test_s5_limitation.py`,
  `test_s6_buyer_cost.py`, `test_invariants.py`, `test_malformed_inputs.py`. Owned by the
  Test author role; engine work must make these pass without editing them.
- `dev/` - 12 unit files, one per engine module.

### 1.8 Frontend (`frontend/`)

Routes (App Router): `/` → `components/dues/DuesScreen.tsx`; `/upload` → `UploadScreen`;
`/eligibility/[id]` → `EligibilityScreen`; `/case/[id]` → `CaseScreen`;
`/case/[id]/pack` → `PackScreen`; `/case/[id]/send/[stage]` → `SendScreen`.

Components: `case/` (CaseScreen, CaseHeader, CaseTabs, EligibilityPill, EligibilityScreen,
EscalationLadder, GuidanceCard, LedgerTable, LimitationCard, LiveInterestTicker, MoneyCard,
NotCovered, ReadingGuide, SectionChip, StatuteTimeline, AssumptionsDrawer, DefensesDrawer),
`cfo/` (CfoCostLines, CfoSettlementOptions, CfoUnavailable), `common/` (Drawer, Icon, Markdown,
Money, States, StatusIcon, TextField), `demo/DemoHint`, `dues/DuesScreen`,
`escalation/` (EscalationTab, LockedStage), `evidence/` (EvidenceTab, EvidenceLocker,
LimitationClock, ReadinessGauge, ChatLines, DefensesPanel, Meaning, TimelineDetail),
`math/` (MathTab, KpiCards, PricingToggles, SettlementSimulator), `pack/PackScreen`,
`send/` (SendPanel, SendScreen), `shell/` (AppShell, Banners, JudgeConsole, PersonaSwitch,
PlaceholderBadge).

Lib: `api.ts`, `useEvaluation.ts`, `caseStore.ts`, `derive.ts`, `demo.ts`, `extraction.ts`,
`fixtures.ts`, `format.ts`, `pageState.ts`, `params.tsx`, `params-parse.ts`, `requestEdits.ts`,
`types.ts`, `useConfig.ts`, `useConnection.ts`, `i18n/{en,kn,index,parse}`.
Generated: `generated/contract-types.ts` (copied from `contracts/types.ts` by
`scripts/sync-contracts.mjs` on predev/prebuild/postinstall/pretypecheck).
`fixtures/` holds the copied contract fixtures + `index.ts`.

Scripts: `dev`, `build`, `lint`, `typecheck`, `check`, `i18n:check`, `i18n:doc`, `smoke`, `sync`.

### 1.9 Makefile targets (`Makefile`)

`dev` (:11, backend only), `backend` (:14), `frontend` (:18, prints "not yet implemented"),
`test` (:22, treats pytest exit 5 as success), `fixtures` (:28, export then copy to
`frontend/fixtures`), `demo` (:32), `openapi` (:38), `types` (:43), `contract-fixtures` (:49),
`contract` (:53, openapi → types → fixtures).

## 2. v4 components: EXISTS / PARTIAL / MISSING

| v4 component | Verdict | Where / why |
|---|---|---|
| `backend/store/` (persistence) | **MISSING** | No directory. Nothing server-side is persisted today: every request rebuilds state. The only "store" in the repo is `frontend/lib/caseStore.ts` (browser `sessionStorage`/`localStorage`) - a name collision, see section 5. |
| `backend/finance/` (financing maths) | **MISSING** | No directory. Closest existing maths is `backend/engine/settlement.py::evaluate_settlement`, which is FROZEN but callable. v4 must call it rather than reimplement. |
| `backend/workflow/` (transition table) | **MISSING** | No directory, no state machine. The only ordering logic is `frontend/lib/derive.ts::currentStage` / `stageLock`, which is display-only and client-side. |
| `backend/ports/` (protocols) | **MISSING** | No directory, no `Protocol`/ABC for eSign, bids or disbursement. |
| `backend/adapters/` (mock/real) | **MISSING** | No directory. The "refuse to start in production with a mock adapter" rule (AGENTS rule 16) has nothing to enforce it. |
| `mock_providers/` (fake financier server) | **MISSING** | No directory. |
| Webhooks (`backend/app/routes/webhooks.py`) | **MISSING** | No route. Signature verification, dedupe and out-of-order parking (AGENTS section 7) are unstarted. `contracts/types.ts:201` is not a route. |
| SSE / `events.py` | **MISSING** | No streaming response anywhere; no `EventSource` in the frontend. `backend/app/main.py` returns plain JSON models only. |
| Options endpoint | **MISSING** | No route of any name. Nearest precedent is `POST /api/v1/simulate-settlement` (`main.py:166`), which is single-scenario, not a two-option comparison. |
| Choice card (frontend) | **MISSING** | No component with "option"/"choice" semantics. Nearest is `components/cfo/CfoSettlementOptions.tsx`, which lists settlement *terms* - a different concept; do not reuse the name. |
| Early flow (frontend) | **MISSING** | The only entry points are `/upload` and the preset-backed `/case/[id]`. No financing entry route. |
| Judge console additions | **PARTIAL** | `components/shell/JudgeConsole.tsx::JudgeConsole` (:290) exists with `judgeCase()` (:50), `LiveResult` (:140), `EditForm` (:164) driving `CaseRequest.config_overrides` (`bank_rate_pct`, `rate_mode`, `appropriation_mode`, `silpi_test_date`). It manipulates the *engine inputs* only; there is no v4 control (no demo-webhook trigger, no option toggle, no store inspection). Gated behind `?judge=1`. |

Adjacent things that DO exist and will be mistaken for v4:

- `POST /api/v1/simulate-settlement` (`main.py:166`, `SettlementSimulationRequest`/`Response`)
  is a one-scenario simulator. It is **not** the two-option model and never recommends.
- `contracts/types.ts` already exports `SettlementTerms`, `SettlementPayment`, `Deferral`,
  `DisclosureFlag`, `PermanentLoss`, `OtherPressurePoint`. These are the vocabulary v4's
  two options will be described in; extending them additively is the cheap path.
- `frontend/components/common/PlaceholderBadge.tsx` and `components/demo/DemoHint.tsx` are the
  existing ways to label non-live data - rule 16's DEMO badge should reuse them, not add a new badge.
- `frontend/components/shell/Banners.tsx::DataBanners` is where `source: "live" | "offline"`
  is surfaced; a `DEMO` source belongs in the same place.

## 3. Integration points that must change

### 3.1 Where the frontend calls `evaluate-case` statelessly

1. **`frontend/lib/useEvaluation.ts:91`** - `const res = await evaluate(request)` inside the
   debounced effect (:80-122). This is the single hook every case view uses. Notes that matter
   for v4:
   - input is resolved client-side by `resolveBase()` (:39): `getUploaded(caseId)` first, else
     `getPresetRequest(caseId)`. There is no server-side case fetch.
   - edits persist to `localStorage` via `setEdited` (:127) and can desync from any v4 store.
   - the offline fallback only fires for **unedited presets** (:100), so a store-backed case
     loses the offline demo path unless it gains a fixture equivalent.
   - `seq.current` (:82) drops stale responses - an SSE-driven view needs the same guard.
2. **`frontend/lib/api.ts:117`** - `evaluate(request: CaseRequest): Promise<CaseResponse>`,
   posting to `/api/v1/evaluate-case` through `call<T>()` (:53) with a timeout + error envelope.
   In offline mode `offlineResponseFor(id)` (:125) reads `frontend/fixtures`.
3. **`frontend/components/dues/DuesScreen.tsx:29`** - `evaluateRow()` calls `evaluate()` **once
   per preset** in `loadRows()`; the dues table is N stateless evaluations on mount. A store-backed
   list should replace this with one read, or the demo will fan out requests it never needed.

### 3.2 Where the extraction Approve step goes

**`frontend/components/upload/UploadScreen.tsx:112 approve()`**
- builds a `CaseRequest` inline (:117-155), mints `const id = \`upload_${Date.now()}\`` (:115),
  calls `saveUploaded(request)` (:156, → `caseStore.ts:48`), then `router.push(href(\`/case/${id}\`))` (:157).
- gated by `canApprove = fieldsOk && detailsOk` (:106); field state comes from
  `frontend/lib/extraction.ts::reviewFields()` (:37) and `REQUIRED_FIELDS` (:22).
- `backend/extraction/confirm.py::ConfirmSpec` already maps every extracted candidate onto a real
  `CaseEvaluationRequest` path, so the backend has the canonical shape; the frontend is currently
  hand-assembling the same object in `approve()`.

This is the seam: v4's "create a case" must become a POST here, and `approve()` should send
`ConfirmSpec`-derived fields rather than construct them locally. The client-minted
`upload_${Date.now()}` id (:115) must be replaced by a server-issued id, which then changes the
meaning of `caseId` everywhere (see 3.4 and section 4).

### 3.3 Where escalation drafts are generated

- **`frontend/components/send/SendPanel.tsx:73`** - `generateArtifact(kind, request, offlineId)`
  inside a `useEffect` keyed on `[kind, request, offlineId, t]`, so **a draft is regenerated on
  every keystroke of an edit**. `kind` comes from `kindFor(stage, request, response)`; `stage` is
  a route param (`/case/[id]/send/[stage]`, `SendStage = 1 | 2 | 3` in `params-parse.ts:8`).
- **`frontend/lib/api.ts:173`** - `generateArtifact(kind, request, offlineId)` → `POST /api/v1/generate-artifact`.
- **`backend/app/main.py:197`** - `generate_artifact()` → `artifacts/generate.py::build_artifact`
  (gated by `artifacts/availability.py::availability`, which decides per-kind whether the stage
  may be drafted at all).
- Stage 4 (evidence pack) is reached from `components/pack/PackScreen.tsx` via `/case/[id]/pack`.

v4 consequence: nothing here is persisted. "Draft generated" is not a state transition, so a
workflow table cannot observe it today. If v4 records draft generation, it must be added around
`main.py:197`, not inside `build_artifact` (golden rule 10: nothing auto-sends; the draft stays
a draft).

### 3.4 Where the Case screen gets its data

`frontend/app/case/[id]/page.tsx` (server component, 13 lines) → `AppShell` → `CaseScreen`
(`components/case/CaseScreen.tsx:33`) → **`useEvaluation(caseId)` and nothing else**.
`<CaseScreen key={id} …>` remounts for a different id (`page.tsx:10`).
Tabs are `CaseTab = "overview" | "evidence" | "math" | "escalation"` (`params-parse.ts:11`),
selected in `CaseScreen.tsx:59` into `CaseTabs`; the `cfo` view reuses the same screen with
`PersonaSwitch`/`View = "supplier" | "cfo"`.

A v4 option comparison therefore has no home yet: it must either become a fifth `CaseTab`
(which changes `parseTab`/`buildHref` and every link that enumerates tabs) or a new route.
The `?judge=1` / `?demo=1` / `?lang=` / `?view=` / `?tab=` / `?step=` / `?send=` params are all
built by `buildHref()` (`params-parse.ts:54`), so a new parameter must be added there or demo
links silently drop it.

## 4. Risks: what in v3 v4 could break

1. **The openapi path-coverage test fails on every new route.**
   `backend/tests/contract/test_openapi_conformance.py:89-95` asserts
   `set(SPEC["paths"]) == READ_PATHS | WRITE_PATHS | UPLOAD_PATHS` (:42-53). Adding an options,
   financing, recovery, webhook or events route to `contracts/openapi.json` makes this test fail
   until that route is added to the sets **and** given a live call in the same file. Every v4
   endpoint costs a conformance-test edit.
2. **`make fixtures` is gated shut right now.**
   `backend/app/export_fixtures.py` gate 1 runs `pytest backend/tests/spec` and refuses to write
   anything unless it exits 0. The spec suite is red (7 findings, section 0.1), so fixtures cannot
   be regenerated today. Any v4 fixture (a two-option response sample, a choice-card fixture)
   inherits that block until F1-F7 are cleared. `make contract` is blocked for the same reason in
   practice, because it ends in `contract-fixtures`.
3. **`make test` is red at baseline** (558 passed, 8 failed). See section 0.1.
4. **Response fixtures are schema-validated.** `test_response_fixtures_match_the_contract`
   (:191) validates every `contracts/fixtures/*.response.json` against the openapi component
   schemas, and `test_request_fixtures_match_the_contract` (:181) does the request side.
   Additive fields are safe; changing an existing field's type or nullability breaks 14 files at once.
5. **Statelessness assumptions that v4 removes.** `useEvaluation` (:63-77, :124-136) assumes the
   request can be rebuilt from `localStorage` (`getEdited`/`setEdited`/`sameRequest`, `caseStore.ts:11-103`),
   that `reset()` can restore `resolved.base`, and that offline mode can fall back to a bundled
   fixture for an unedited preset (:100). A store-backed case has a server truth, so `reset`,
   `isEdited`, `offlineId` and the `key={id}` remount all need a decision.
6. **Case identity.** `case_id` is either a preset id (`case_01`) or a client timestamp
   (`UploadScreen.tsx:115`). A server store cannot keep both. Changing it touches
   `frontend/fixtures/index.ts`, `lib/fixtures.ts`, `demo.ts::DEMO_START_CASE` (`"case_01"`),
   `demo.ts::DEMO_STEPS`, and `scripts/smoke.mjs`'s route list.
7. **URL params are load-bearing for the demo.** `?demo=1` (`lib/demo.ts`, `parseDemo`),
   `?judge=1` (`parseJudge`), `?lang=kn|en`, `?view=supplier|cfo`, `?tab=`, `?step=`, `?send=`.
   `scripts/smoke.mjs` asserts 37 routes + demo steps. Any new screen that mints its own query
   string instead of calling `useHref()`/`buildHref()` will break the demo walkthrough.
8. **The contract mirror is generated on every dev/build.** `frontend/scripts/sync-contracts.mjs`
   runs on `predev`, `prebuild`, `postinstall`, `pretypecheck` and copies `contracts/types.ts` →
   `frontend/generated/contract-types.ts`. Hand-editing the generated copy is silently reverted;
   `contracts/types.ts` is the only source of truth.
9. **Frontend typecheck is already red.** `docs/review-2026-10-25.md` blocker B1:
   `components/pack/PackScreen.tsx:18 BAND_TONE` has 3 keys against the 4-member `ReadinessBand`
   union (`contracts/types.ts:760`). `npm run typecheck` therefore fails before v4 starts, so
   "frontend is green" is not a usable baseline either.
10. **Engine freezing is real.** `AGENTS.md:47` forbids changing `backend/engine/**` and forbids the
    v4 roles from editing `backend/finance/**` after it exists. Adding a field to
    `CaseEvaluationResponse` for v4 convenience is an engine change and is out of bounds; v4 must
    compose above `evaluate_case`, exactly as `artifacts/` already does.
11. **Mock-safety rules have no enforcement point yet.** AGENTS rules 16-18 (DEMO badge,
    `X-Simulation: true`, `MOCK`-prefixed ids, no Aadhaar, refuse to start in production with a
    mock adapter) describe an app factory that does not exist. `backend/app/main.py:41` builds a
    single `FastAPI()` with no settings object to branch on.
12. **Golden rule 20 (never recommend) and rule 21 (financier cannot enforce MSMED rights) are
    copy-level traps.** The existing UI already avoids both, but a two-option card is precisely
    where a "recommended" badge or a "legal recourse" line would slip in. The i18n gate
    (`scripts/i18n-check.mjs`, 619 en keys) plus `docs/claims-register.md` - **which also does not
    exist** - are the only guards named in AGENTS rule 13.

## 5. Existing names to reuse (so later prompts do not duplicate)

### Backend

| Name | Home | Reuse for |
|---|---|---|
| `evaluate_case(config, request)` | `engine/evaluate.py:178` | the only legal-maths entry |
| `StatuteConfig`, `load_config(path)` | `engine/config.py:177`, `app/config_loader.py:44` | config injection; never a constant |
| `objection_window(config)` | `app/config_loader.py:63` | passing a statutory number without holding one |
| `build_artifact(...)`, `ArtifactResult` | `artifacts/generate.py:53,42` | any new draft |
| `availability(...)` | `artifacts/availability.py:43` | "may this be drafted yet" gate |
| `ArtifactKind`, `STAGE_BY_KIND`, `KIND_TITLES` | `artifacts/kinds.py` | stage naming; add a member rather than a parallel map |
| `ConfirmSpec` | `extraction/confirm.py:19` | field→request-path mapping for the Approve step |
| `_error(code, message, status, field)` | `app/main.py:54` | the `{error:{code,message}}` envelope |
| `CaseEvaluationRequest/Response`, `SettlementSimulationRequest/Response`, `SettlementTerms`, `ArtifactGenerationRequest/Response`, `ExtractionResponse`, `ExtractedField`, `ExtractedMessage`, `ConfirmEntry`, `Warning`, `Citation` | `contracts/types.ts` | extend additively |
| `/api/v1/<kebab-case>` prefix | `contracts/openapi.json` | new route naming |
| `SCREAMING_SNAKE` warning codes (`PLACEHOLDER_DATA`, `GRN_MISSING_DEEMED_ACCEPTANCE`) | `schemas.py`, `lib/derive.ts:17-18` | new warning codes |
| `evaluate_settlement` | `engine/settlement.py` | the two options' sideways maths (call it) |

### Frontend

| Name | Home | Reuse for |
|---|---|---|
| `useEvaluation(caseId)` → `Evaluation` | `lib/useEvaluation.ts:50` | case data; extend the return rather than add a second hook |
| `evaluate`, `Sourced<T>`, `Source`, `ApiError`, `BackendUnreachable` | `lib/api.ts:117,21,22` | every call |
| `useHref()`, `useUrlState()`, `UrlState`, `parseTab`/`buildHref` | `lib/params.tsx:29,25`, `lib/params-parse.ts:54` | new params and links |
| `useT()`, `tWarning()` | `lib/i18n/index.tsx` | every user-visible string |
| `Money`, `Drawer`, `StatusIcon`, `Icon`, `EmptyState`/`Skeleton`/`ErrorState` | `components/common/` | new card chrome |
| `PlaceholderBadge`, `DemoHint`, `DataBanners` | `components/{shell,common,demo}/` | the DEMO badge and source banner |
| `judgeCase`, `JudgeCase`, `JudgeConsole` | `components/shell/JudgeConsole.tsx:50,37,290` | judge-console additions |
| `isPlaceholder`, `eligibilityTone`, `currentStage`, `stageLock`, `hasCode`, `recommendedWhy` | `lib/derive.ts` | display derivation (never maths) |
| `format.ts` helpers (`count`, ...) | `lib/format.ts` | formatting at the edge only |
| `getEdited`/`setEdited`/`getUploaded`/`sameRequest` | `lib/caseStore.ts` | local edit persistence, until a store replaces it |
| preset ids `case_01`…`case_06`, `DEMO_START_CASE`, `DEMO_STEPS` | `backend/presets/`, `lib/demo.ts:24,26` | fixtures and demo script |

### Names already taken - do not create a second one

- `caseStore` (`frontend/lib/caseStore.ts`) is the browser store. A backend `store` package is
  fine, but do not name a frontend module `store.ts` or expose `useCaseStore` for server data.
- `settlement` is engine-owned (`engine/settlement.py`, `SettlementTerms`, `simulate-settlement`).
  A v4 concept that happens to be a settlement of a different kind needs its own noun.
- `option` / `choice` / `financing` / `financier` / `workflow` / `transition` / `port` / `adapter`
  are **unused** in code today - free to claim, but claim each in exactly one home.

## 6. Open question raised by this report

| id | Question | Why it blocks |
|---|---|---|
| OQ-V4-1 | `docs/architecture_v4_two_options.md` does not exist. Is v4 defined by a document still to be captured (like V1-V11), or by `AGENTS.md` section 3 plus the prompt? | Sections 2 and 3 name components but cannot name their shapes (option payloads, transition table rows, SSE event names, store schema). Building them from the prompt alone risks inventing a design and then rewriting it. |

Suggested resolutions, in the order that unblocks the most work:

1. Land `docs/architecture_v4_two_options.md` (or confirm AGENTS section 3 is the spec).
2. Decide whether F1-F7 get fixed before v4, because `make test` and `make fixtures` are both red.
3. Fix B1 (`PackScreen.tsx:18`) so the frontend typecheck baseline means something.
4. Wire `make dev`/`make frontend` (CR-12) so "keep `make dev` green" is a real check.
