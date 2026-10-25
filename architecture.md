# SamadhaanOS Architecture (aligned to spec v3.1)

Audience: Aniruddha (backend), Mochi (frontend), and every AI agent working in this repo.
Status: **contract v1.0 is frozen once S1 in `prompts.md` is merged.** Changes after that go through the change protocol in section 9.

> **v4 extension:** `docs/architecture_v4_two_options.md` adds the two-option model on top of this
> document — a financing track alongside the recovery ladder, plus the store, finance, workflow,
> ports/adapters, mock providers, webhooks, SSE and `contract v1.1` (additive) they need.
> Everything here still applies; where the two differ, v3.x wins for the legal engine and the
> v4 document wins for the new infrastructure. Its open questions are OQ-10 to OQ-14 in
> `docs/open-questions.md`; the webhook, state-machine and threat-model extracts live in
> `docs/webhooks.md`, `docs/state-machines.md` and `docs/threat-model.md`.

---

## 1. Principles (non-negotiable)

1. **LLM at the edges, law at the core.** The legal-math path (eligibility, dates, interest, tax timing, limitation) contains no LLM and no network calls.
2. **Config over constants.** Every statutory value lives in `backend/config/statute_config.json` with a `source_ref` and a `verified` flag. No magic numbers in code.
3. **Contract first.** Backend and frontend build in parallel against the frozen contract. The frontend never computes legal numbers. It formats what the engine returns.
4. **Every on-screen number comes from the engine.** Mock fixtures are placeholders and are visibly labelled until replaced by engine output.
5. **Offline-first.** The demo must run on a laptop with no internet. Extraction has a regex path. The frontend has bundled fixtures.
6. **Open questions are shown, not hidden.** Unverified or interpretive rules surface in `assumptions[]` and `warnings[]` and in the UI's assumptions drawer.
7. **Synthetic data only.** No real parties, no real Udyam or GSTIN numbers.

---

## 2. System overview

```
                    +---------------------------- FRONTEND (Next.js + Tailwind) ---------------------------+
                    |  Top bar: case, eligibility pill, persona switch, judge console, EN/KN toggle        |
                    |  Supplier workspace: Evidence+Timeline | The Math | Escalation+Dossier               |
                    |  Buyer CFO view (same data, advisory tone)                                           |
                    |  api client -> /api/v1/*   (fallback: bundled fixtures when API unreachable)         |
                    +------------------------------------------+-------------------------------------------+
                                                               | JSON (contract v1.0, decimals as strings)
                    +------------------------------------------v-------------------------------------------+
                    |                        BACKEND API (FastAPI + Pydantic v2)                            |
                    |  /evaluate-case  /presets  /simulate-settlement  /generate-artifact  /config         |
                    |  /extract-evidence (stretch)  /health                                                |
                    +--------------+----------------------------+----------------------------+-------------+
                                   |                            |                            |
                    +--------------v---------+   +--------------v------------+   +-----------v-------------+
                    |  ENGINE (pure Python)  |   |  ARTIFACTS (md + PDF)     |   |  EXTRACTION (optional)  |
                    |  gate, acceptance,     |   |  stage 1-4 templates      |   |  regex first, LLM edge, |
                    |  s.15, s.16 ledger,    |   |  BSA s.63 template        |   |  human-confirm schema,  |
                    |  buyer cost, limitation|   +---------------------------+   |  cached demo mode       |
                    |  defenses, readiness   |                                   +-------------------------+
                    +--------------+---------+
                                   |
                    +--------------v---------+
                    |  statute_config.json   |  <- filled from docs/statute-sheet (printed primary sources)
                    +------------------------+
```

---

## 3. Repo layout

```
Srujana_hackathon2026_SamadhaanOS/
  AGENTS.md                      # copy of docs/agents.md (agents read this first)
  README.md
  Makefile                       # make dev | make test | make fixtures | make demo
  backend/
    app/                         # FastAPI: main.py, routes, schemas (Pydantic), error handling
    engine/                      # PURE functions, no I/O, no clock, no network
      config.py                  # loads + validates statute_config.json
      money.py  dates.py         # Decimal helpers, month-rest stepping
      gate.py                    # eligibility gate
      acceptance.py              # s.2(b) state machine + s.15 clamp + due dates
      interest.py                # s.16 ledger, rate epochs, part-payments
      buyer_cost.py              # permanent loss, FY checkpoints, deferral cost
      limitation.py              # limitation clock
      defenses.py                # buyer-defenses panel
      readiness.py               # evidence readiness score
      settlement.py              # split + waiver arithmetic
      evaluate.py                # orchestrates the above into CaseEvaluationResponse
    artifacts/                   # stage templates, markdown + PDF rendering
    extraction/                  # stretch: whatsapp parser, field extractors, confirm schema
    config/statute_config.json
    presets/                     # INPUT-only preset cases (case_01.json ... case_06.json)
    tests/
      spec/                      # written by the independent test author (never by the engine author)
      dev/                       # engine author's own smoke tests
      contract/                  # schema/fixture validation
  frontend/
    app/                         # Next.js App Router
    components/                  # TopBar, PersonaSwitch, JudgeConsole, Timeline, LedgerTable, ...
    lib/api.ts  lib/format.ts  lib/i18n/{en,kn}.ts
    fixtures/                    # copied from contracts/fixtures by `make fixtures`
  contracts/
    openapi.json                 # exported from FastAPI, source of truth
    types.ts                     # generated from openapi.json
    fixtures/                    # <preset>.request.json, <preset>.response.json (engine-generated)
  docs/
    statute-sheet/               # printed primary sources + screenshots (V1..V11)
    event-rules.md               # organizer clauses pasted verbatim (V11)
    architecture.md  agents.md  prompts.md
    open-questions.md  review-*.md  worklog.md
```

---

## 4. Ownership split

| Area | Backend (Aniruddha + backend agents) | Frontend (Mochi + frontend agent) | Shared |
|---|---|---|---|
| Legal rules and math | Owns all of it | Never computes legal values | Reviews assumptions text together |
| statute_config.json | Owns, fills from statute sheet | Reads via `/config` for the assumptions drawer | Statute sheet verified by both |
| API contract | Owns Pydantic models, exports OpenAPI | Consumes generated `types.ts` | Change protocol (section 9) |
| Presets | Owns input files and engine-generated outputs | Consumes fixtures, wires judge console | Agree on the demo order |
| Artifacts (Stage 1-4) | Owns content and PDF | Owns preview, share, print layout | Owner approves wording |
| Extraction | Owns (stretch) | Owns confirm-fields UI | Confirm schema |
| i18n | Provides plain-language strings per rule id | Owns EN/KN dictionaries and the toggle | Native Kannada review |
| Tests | Engine tests (spec/ by a separate author) | Component and e2e smoke | Rehearsed judge manipulations |
| Demo and README | Test output, limitations | Demo flow, screen recording | AI-disclosure section |

---

## 5. Statute config

One file, typed loader, every entry shaped like:

```
{ "value": <...>, "source_ref": "V2:s.15 proviso", "verified": false, "note": "" }
```

Keys (the loader fails fast if any key is missing):

| Key | Meaning | Prefill | Verify via |
|---|---|---|---|
| `interest_multiplier` | s.16 multiple of Bank Rate | 3 | V2 |
| `objection_window_days` | s.2(b) written-objection window | 15 (expected) | V2 |
| `credit_cap_days` | s.15 proviso cap on a written agreed period | 45 | V2 |
| `no_agreement_days` | s.15 period when no written agreement | 15 | V2 |
| `bank_rate_epochs[]` | `{from, bank_rate_pct}` ascending | 5.75 from 2026-10-07 per news reports. 5.50 was in force in Apr and Aug 2026 per news reports. **Fill earlier epochs from RBI.** | V1 |
| `size_epochs[]` | micro/small/medium investment and turnover limits by `from` date | 2025-04-01: micro 2.5/10, small 25/100, medium 125/500 (crore). Earlier set: 1/5, 10/50, 50/250. | V6 |
| `silpi_test_date` | `CONTRACT` or `SUPPLY` | null until read | V4 |
| `trader_nic_prefixes` | NIC divisions treated as trading | 45, 46, 47 | V5 |
| `limitation_years` | limitation for the price of goods or services | null until read | V7 |
| `section_43bh_first_fy` | first FY where 43B(h) applies | 2023-24 | V3 |
| `rate_mode_default` | `FLOATING` or `FROZEN_AT_APPOINTED_DAY` | FLOATING | open (OQ-4) |
| `appropriation_mode_default` | `INTEREST_FIRST` or `PRINCIPAL_FIRST` | INTEREST_FIRST | open |
| `payment_boundary_convention` | how a mid-period payment is treated | `PAYMENT_DATE_IS_REST_BOUNDARY` | open (OQ-3) |
| `day_count_fraction_days` | days in a year for stub interest | 365 | convention |
| `tax_presets[]` | buyer tax-rate presets for the UI | company 115BAA 25.168, other 31.2 | V3, verify |
| `gated_features` | `{gst_itc_180d, msme1_return, s19_deposit}` booleans | all false | V9 |

If a needed constant is `null` or `verified: false`, the engine still runs but adds a `warnings[]` entry (`UNVERIFIED_CONSTANT`) naming the key. A `STRICT_VERIFIED=1` env flag turns those into errors. Run strict before the demo video.

---

## 6. Engine design

Rules for everything under `backend/engine/`:

- **Pure functions.** No file I/O (config is passed in), no `datetime.now()`, no randomness, no network. The calculation date always arrives in the request.
- **Money is `decimal.Decimal`.** Rates and percentages are Decimal. JSON carries them as strings. No floats anywhere in the legal path.
- **Rounding:** quantize to 0.01 with `ROUND_HALF_UP` at each ledger row, so the ledger sums exactly. Document this on screen.
- **Dates are `datetime.date`.** Only the `Z`-less ISO form `YYYY-MM-DD` crosses the API boundary.
- **Every rule emits a citation.** Each result block carries `citations[]` entries `{id, rule, statute_ref, config_key, verified}`.
- **Never silently guess.** Missing or conflicting inputs produce a status plus a `warnings[]` entry, not a default.

### 6.1 Eligibility gate (`gate.py`)
Checks, in order, each returning `{id, passed: true|false|null, detail, rule_ref}`:
1. `enterprise_class` on the supply date, looked up in `size_epochs`. Medium and above fail. Reverse graduation noted.
2. `silpi_chronology` using `silpi_test_date` (CONTRACT or SUPPLY). If the config value is null, the check returns `null` with an `OPEN_QUESTION` warning, not a pass.
3. `trader_exclusion` from NIC prefixes in `trader_nic_prefixes`.
4. `activity_match` is a risk flag only, never a block.

Status precedence for the pill: `BARRED_SILPI` > `EXCLUDED_TRADER` > `EXCLUDED_MEDIUM` > `INSUFFICIENT_DATA` > `ELIGIBLE`. Ineligible results include `alternative_remedy` text (civil summary suit, Order XXXVII CPC, Commercial Courts Act) and **skip the interest and buyer-cost blocks** (they return `null`).

### 6.2 Acceptance and due dates (`acceptance.py`)
- Anchor on `delivery_date`. If `delivery_date` is null, status `NO_DELIVERY_PROOF`: no acceptance, no due date, readiness capped, Stage 1 cure note recommended.
- Window end = delivery date + `objection_window_days`.
- Written objection with `raised_date <= window_end`: status `PENDING_RESOLUTION` until `resolved_date` exists, then acceptance = `resolved_date`. Objections that are not written, or raised after the window, are listed in `late_complaints` and do not move the clock.
- No qualifying objection: acceptance = delivery date (deemed acceptance).
- Applied period: no written agreement means `no_agreement_days`. Otherwise `min(agreed, credit_cap_days)`. `clamped = agreed > cap`.
- `due_date = acceptance + applied_days`. `appointed_day = due_date + 1`.
- **No regime logic.** The cap applies to every supply.

### 6.3 Interest ledger (`interest.py`)
- Statutory rate on any day = `interest_multiplier x bank_rate(day)`.
- `rate_mode`: `FLOATING` splits at epoch boundaries and uses the epoch rate for each segment. `FROZEN_AT_APPOINTED_DAY` uses the epoch rate on the appointed day for the whole period.
- Monthly rests: rest dates are `appointed_day + k calendar months` (end-of-month clamped). At a rest, accrued interest is added to the balance. The balance has two buckets, principal and interest, and **compounding applies to their sum**.
- Stub: days since the last rest to the calculation date accrue simple interest at `rate x days / day_count_fraction_days`.
- Part-payment (convention `PAYMENT_DATE_IS_REST_BOUNDARY`): accrue the stub up to the payment date, capitalize it, apply the payment, then start a new rest cycle from the payment date. The convention is shown on screen and flagged for lawyer review (OQ-3).
- Appropriation: `INTEREST_FIRST` reduces the interest bucket, then principal. `PRINCIPAL_FIRST` is the reverse. The total balance is identical in both modes. Only the principal/interest split changes, and that split feeds the 43B(h) base.
- Output: `ledger[]` rows, `rate_segments[]`, totals, and `daily_accrual` (interest per day on the calculation-date balance) so the UI ticker needs no legal math.
- Payment before the appointed day, or exceeding the balance, are defined edge cases with tests (see section 11).

### 6.4 Buyer cost (`buyer_cost.py`), three separate lines, never summed
1. **Permanent loss:** interest accrued is non-deductible. Also `pretax_equivalent_rate_pct = statutory_rate / (1 - buyer_tax_rate)`.
2. **Deferral:** for each FY end (31 March) in `[due_date, calculation_date]` where principal is still outstanding past the s.15 limit, report `unpaid_principal`, `tax_timing_effect = unpaid_principal x tax_rate`, and `deferral_cost = tax_timing_effect x cost_of_capital x years_deferred`. `cost_of_capital_pct` and `years_deferred` are request inputs with UI defaults. Applies only if the FY is on or after `section_43bh_first_fy`.
3. **Disclosure flags:** s.22 disclosure in audited accounts. Plus items from `gated_features`, **emitted only when that flag is true**.

### 6.5 Limitation (`limitation.py`)
`expiry = due_date + limitation_years`, restarted by qualifying `acknowledgments[]` (`is_signed` true and kind in signed balance confirmation or part-payment). WhatsApp promises are recorded as `potential_acknowledgment` and never restart the clock. Status bands: `OK`, `WARN_12M`, `WARN_6M`, `EXPIRED`, `UNKNOWN` (when `limitation_years` is null).

### 6.6 Defenses and readiness
`defenses.py` maps buyer arguments to rule refs, evidence held and missing, using engine state. Arbitration-clause and set-off rows are always `OPEN_QUESTION`. `readiness.py` returns a 0-100 score with `reasons[]` (each code, delta, text), blocked stages, and the recommended stage. Missing delivery proof caps the score and blocks Stage 4.

---

## 7. Demo-critical facts to get right

- Delivery date, not invoice date, anchors acceptance.
- A "Net 90" PO is clamped to the s.15 cap and flagged as a contract override.
- The 43B(h) timing effect is **not** added to interest loss.
- Stage 4 is a portal-fields checklist plus evidence bundle, **not** a fabricated official form.
- Medium and trader suppliers, and Silpi-barred cases, are stopped at the gate with an honest explanation.

---

## 8. API contract v1.0

Conventions: JSON; dates `YYYY-MM-DD`; money, rates and percentages are **decimal strings** (`"1250000.00"`, `"17.25"`); enums are UPPER_SNAKE; every response includes `contract_version`.

### 8.1 Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | liveness, config load status |
| `GET /api/v1/config` | statute config for the assumptions drawer, with `verified` flags |
| `GET /api/v1/presets` | list preset ids and titles |
| `GET /api/v1/presets/{id}` | the preset's **request** (input only) |
| `POST /api/v1/evaluate-case` | request in, full evaluation out |
| `POST /api/v1/simulate-settlement` | `{case request or evaluation ref, upfront_pct, waiver_pct, days_to_second_payment}` in, split arithmetic out |
| `POST /api/v1/generate-artifact` | `{kind, request}` in, `{filename, markdown, pdf_base64?}` out |
| `POST /api/v1/extract-evidence` | stretch: multipart in, candidate fields plus citations plus confirm schema out |

Error model for all endpoints: `{error: {code, message, field?}}` with HTTP 422 for validation, 400 for rule violations, 500 otherwise. The engine never returns a partial block silently: a block is either present, `null` with a reason in `warnings[]`, or the request fails validation.

### 8.2 `CaseEvaluationRequest`

```
contract_version: "1.0"
case_id: string
supplier:
  name: string
  udyam_number: string | null
  enterprise_class: MICRO | SMALL | MEDIUM | UNKNOWN
  activity: MANUFACTURING | SERVICES | TRADING
  nic_codes: string[]
  udyam_registration_date: date | null
  investment_cr: decimal | null
  turnover_cr: decimal | null
buyer:
  name: string
  gstin: string | null
  tax_rate_pct: decimal            # UI presets from config tax_presets
  cost_of_capital_pct: decimal     # default from UI
transaction:
  contract_date: date | null       # PO or agreement date
  supply_date: date | null         # defaults to delivery_date
  invoice_date: date
  delivery_date: date | null       # null = no delivery proof
  principal: decimal
  written_credit_days: int | null  # null = no written agreement
  calculation_date: date
  years_deferred: decimal | null   # input for deferral cost
objections: [{ raised_date: date, is_written: bool, description: string | null, resolved_date: date | null }]
part_payments: [{ date: date, amount: decimal, reference: string | null }]
acknowledgments: [{ date: date, kind: SIGNED_BALANCE_CONFIRMATION | PART_PAYMENT | WHATSAPP_PROMISE, is_signed: bool, source_ref: string | null }]
evidence: { items: [{ kind: PO | INVOICE | DELIVERY_PROOF | WHATSAPP | UDYAM | GST_RETURN, present: bool, ref: string | null }] }
config_overrides: { bank_rate_pct?: decimal, objection_window_days?: int, rate_mode?: ..., appropriation_mode?: ..., silpi_test_date?: CONTRACT | SUPPLY } | null
```

### 8.3 `CaseEvaluationResponse`

```
contract_version, case_id, calculation_date
jurisdiction:
  status: ELIGIBLE | BARRED_SILPI | EXCLUDED_TRADER | EXCLUDED_MEDIUM | INSUFFICIENT_DATA
  eligible: bool
  checks: [{ id, passed: bool | null, detail, rule_ref }]
  alternative_remedy: string | null
timeline:                            # null if gate blocks AND no dates computable
  delivery_date, objection_window_end
  objection_status: DEEMED_ACCEPTANCE | PENDING_RESOLUTION | RESOLVED | NO_DELIVERY_PROOF
  acceptance_date: date | null
  agreed_days: int | null, applied_days: int | null, clamped: bool
  due_date: date | null, appointed_day: date | null, days_overdue: int | null
  late_complaints: [{ date, description, reason }]
financials:                          # null if ineligible
  rate_mode, appropriation_mode, payment_boundary_convention
  rate_segments: [{ from, to, bank_rate_pct, statutory_rate_pct }]
  ledger: [{ kind: REST | PAYMENT | STUB, from, to, opening, interest, payment, closing, rate_pct, note }]
  interest_total, principal_outstanding, interest_outstanding, total_claim
  daily_accrual                      # interest per day on the calculation-date balance
buyer_cost:                          # null if ineligible
  permanent_loss: { interest_non_deductible, pretax_equivalent_rate_pct }
  deferral: { applies: bool, checkpoints: [{ fy_end, unpaid_principal, tax_timing_effect }], deferral_cost: decimal | null, inputs: { cost_of_capital_pct, years_deferred } }
  disclosure_flags: [{ id, text, verified }]
  other_pressure_points: [{ id, text }]          # only if gated feature verified
limitation: { expiry: date | null, status, events: [{ date, kind, restarts_clock: bool }] }
defenses: [{ id, buyer_says, rule_ref, status: STRONG | AT_RISK | OPEN_QUESTION, evidence_have: string[], evidence_missing: string[] }]
evidence_readiness: { score: int, band: COURT_READY | ACTION_NEEDED | BLOCKED, reasons: [{ code, delta, text }], missing: string[], blocked_stages: int[], recommended_stage: int }
citations: [{ id, rule, statute_ref, config_key, verified: bool }]
assumptions: string[]
warnings: [{ code, severity: INFO | WARN | BLOCK, text }]
```

Plain-language copy: every `rule_ref`, `reasons[].code` and `warnings[].code` has an i18n key on the frontend (`rules.<code>.title`, `rules.<code>.plain`). Backend returns codes plus an English `text`. The frontend translates by code and falls back to `text`.

---

## 9. Contract change protocol

1. Contract v1.0 is exported to `contracts/openapi.json` and tagged `contract-v1`.
2. Any field change: backend edits Pydantic models, re-exports OpenAPI, regenerates `contracts/types.ts`, bumps `contract_version` minor (1.1), and notes it in `docs/worklog.md`.
3. Only **additive** changes are allowed after the 17:30 checkpoint. Removing or renaming a field needs both humans to agree in writing.
4. CI-style check (`make test`) validates all fixtures against the schema, so drift fails loudly.

---

## 10. Frontend architecture

- **Stack:** Next.js (App Router), TypeScript, Tailwind, Recharts for charts. Types come from `contracts/types.ts`.
- **State:** one `useEvaluation(request)` hook (debounced POST, last-good result retained, error and offline states). Persona and language in URL params (`?view=supplier|cfo&lang=en|kn`) so a demo state can be linked or reset.
- **Offline-first:** `lib/api.ts` tries the API, then falls back to `frontend/fixtures/<preset>.response.json` and shows an **"Offline demo data"** banner. Custom edits in offline mode show a clear "recompute needs the backend" message rather than faking numbers.
- **No legal math.** `lib/format.ts` only formats (Indian digit grouping, dates, percentages). The live ticker multiplies `financials.daily_accrual` by elapsed seconds, nothing more.
- **Components:** `TopBar`, `EligibilityPill`, `PersonaSwitch`, `JudgeConsole` (presets plus mutation form), `StatuteTimeline`, `EvidenceLocker` (manual entry MVP), `ReadinessGauge`, `LedgerTable`, `KpiCards`, `BuyerCostLines`, `LimitationClock`, `DefensesPanel`, `EscalationStepper`, `ArtifactPreview`, `AssumptionsDrawer`, `LangToggle`.
- **UX rules:** plain-language "what this means for you" card for every block. Ineligible and blocked states are first-class screens, not error toasts. The CFO view has zero legal-threat language and never shows a single combined loss.
- **Accessibility:** keyboard navigable drawers, visible focus, colour never the only signal (icon plus text on every status), contrast checked for both persona themes.
- **i18n:** `en.ts` is complete. `kn.ts` covers the MVP card set (about 12 strings), with legal terms kept in English in brackets. Missing keys fall back to English.

---

## 11. Testing architecture

| Layer | Who writes it | What it proves |
|---|---|---|
| `tests/spec/` | **Independent test author** (separate agent or person, working from the statute sheet and this document, **not reading `engine/`**) | Rule correctness on round-number, hand-computed cases |
| `tests/dev/` | Engine author | Smoke and regression while building |
| `tests/contract/` | API agent | Every fixture and every endpoint response validates against the schema |
| Frontend smoke | Frontend agent | Each persona and each preset renders without errors in both languages and in offline mode |
| Judge manipulations | Both humans, rehearsed | The five live edits produce correct output in under a second |

Required edge cases in `tests/spec/`: delivery later than invoice; no delivery proof; objection on the last day of the window and the day after; objection unresolved; written vs non-written objection; no agreement vs Net 90 vs Net 30; leap-year Feb dates and month-end rests; payment before the appointed day; payment larger than the balance; payment on a rest date; two payments; bank-rate change mid-delay under both rate modes; epoch boundary dates; medium, trader and Silpi blocks; limitation restart by signed confirmation but not by WhatsApp; 31 March checkpoint with partial payment before it; Decimal rounding totals equal the sum of rows.

**Do not use v2's worked CASE-01 numbers as an oracle.** See section 12.

---

## 12. Known traps (read before building)

1. **v2's worked ledger is not a valid test oracle.** It applies 17.25% for the whole of Dec 2025 to Apr 2026. News reports put the Bank Rate at 5.50% in April and August 2026, and 5.75% only from 7 Oct 2026. Under `FLOATING` mode, CASE-01 as specified (calculation date 15-Apr-2026) uses the 5.50% epoch, giving 16.5%. Fill `bank_rate_epochs` from RBI (V1) and regenerate every figure from the engine. If you want the 17.25% rate on screen, choose a calculation date after 7 Oct 2026 and say so.
2. Never reintroduce "regime OLD/NEW". The 45-day cap is in the s.15 proviso for all supplies.
3. Never present one combined "buyer loss" number.
4. Never generate a document that looks like an official form. Stage 4 is a checklist plus evidence bundle.
5. Never send or auto-send anything. The owner approves every artifact, and the app only produces drafts.
6. Do not assume 15 vs 30 days, the Silpi test date, or the limitation period. Read V2, V4, V7.

---

## 13. Open questions (track in `docs/open-questions.md`)

| ID | Question | Default until resolved | Owner |
|---|---|---|---|
| OQ-1 | Objection window: 15 days? Deemed acceptance anchored on delivery? | 15 and delivery, flagged | Aniruddha (V2) |
| OQ-2 | Silpi test date: contract or supply, and later supplies under an older contract | config null, gate returns `null` plus warning | Aniruddha (V4) |
| OQ-3 | Mid-period part-payment convention | payment date is a rest boundary, shown on screen | Aniruddha |
| OQ-4 | s.16 rate frozen at appointed day vs floating | FLOATING, toggleable | Aniruddha |
| OQ-5 | What counts as a "written agreement" (PO, email chain) | PO or signed document counts, assumption shown | Aniruddha |
| OQ-6 | Limitation period and acknowledgment rules | config null, status UNKNOWN | Aniruddha (V7) |
| OQ-7 | Arbitration clause and set-off interplay | `OPEN_QUESTION` row, never asserted | Aniruddha |
| OQ-8 | V9 buyer-pressure rules (GST credit reversal, MSME-1, appeal deposit) | gated off | Aniruddha |
| OQ-9 | Evaluation cadence, start time, video rules | per V11 | both |

---

## 14. Definition of done

A task is done only when: the code runs, the relevant tests pass, no unverified constant is silently relied on, the contract is unchanged (or changed via section 9), the worklog entry is written, and the person who did not write it can explain what it does.
