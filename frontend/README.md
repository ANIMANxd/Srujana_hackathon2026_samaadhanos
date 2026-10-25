# SamadhaanOS frontend

Next.js (App Router) + TypeScript strict + Tailwind v4. Built to
`docs/frontend-structure.md` v3.3: a **journey** of screens rather than one
dashboard. The frontend never computes legal numbers. It formats what the
engine returns (AGENTS.md golden rule 6).

## Run

```bash
cd frontend
npm install          # also syncs ../contracts into generated/ and fixtures/
npm run dev          # http://localhost:3000
```

With the backend running (`make backend` in the repo root, port 8000), every
screen uses live engine output and the top bar says **Engine live**. Without it,
a persistent **"Offline demo data"** banner sits under the top bar: preset cases render the engine
output saved in `contracts/fixtures/` (including the draft samples), the upload
samples show the extractor's saved results, and edited or uploaded cases say
"Recompute needs the backend" instead of showing numbers.

**Demo:** open `/?demo=1` for the scripted 60-second run (CASE-01 supplier,
Buyer CFO, CASE-02, CASE-05). It hides the judge-console button and adds a small
fixed hint strip; it never changes data. The pass and recording tips are in
[`DEMO.md`](./DEMO.md).

| Env var | Default | Purpose |
|---|---|---|
| `BACKEND_URL` | `http://127.0.0.1:8000` | Where `/api/v1/*` is proxied (no CORS needed) |

## Scripts

| Script | What it does |
|---|---|
| `npm run sync` | Copies `../contracts/types.ts` → `generated/contract-types.ts`, and `../contracts/fixtures/*` plus the extractor's demo samples → `fixtures/` (both git-ignored). Runs automatically before dev, build and typecheck |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint (Next core-web-vitals + TypeScript) |
| `npm run i18n:check` | Language-toggle test without a browser: every owner-facing card key has Kannada or falls back to English, MVP coverage, placeholders, and the CFO view stays English |
| `npm run i18n:doc` | Regenerates `docs/kannada-review.md` from `en.ts`/`kn.ts` for the native speaker |
| `npm run build` | Production build |
| `npm run check` | typecheck + lint + build: run before every push |
| `npm run smoke` | With a server running, requests every route and fails on non-200 or error markers; also runs the visible `?lang=kn` / `?lang=en` toggle checks |

## Screens

| Route | Question it answers |
|---|---|
| `/` Dues | Who owes me, how late, what first? |
| `/upload` | Did the app read my invoice, PO or WhatsApp export correctly? (.txt; approve before anything is used) |
| `/case/[id]` | What's happening with this invoice and what do I do now? (guidance card, timeline, money, ladder) |
| `/case/[id]?tab=evidence` | What do I hold, and what did the engine make of it? (evidence locker with a WhatsApp line viewer, full statutory timeline, readiness gauge with locked stages explained, defenses, limitation bands; each with a "what this means for you" card) |
| `/case/[id]?tab=math` | How was the number worked out? (KPI cards with rate segments, rate-mode and appropriation toggles re-run through config_overrides with the engine's own explanation, expandable ledger, assumptions drawer, settlement simulator via /simulate-settlement) |
| `/case/[id]?tab=escalation&step=n` | What do I send next, and why? (four-step stepper; each step previews the backend draft labelled DRAFT, with copy, WhatsApp, email, backend PDF or a print fallback, all enabled only after "I have reviewed this draft"; locked steps explain why in the engine's words; Stage 4 is a checklist and evidence bundle with a portal-fields note) |
| `/case/[id]?view=cfo` | What does the buyer's finance team see? (same evaluation, advisory tone: three separate cost lines, never summed; deferral explained as deferred, not lost; interest accruing at the statutory rate; settlement option cards with a link to the Stage 3 term sheet; an honest "cost view not available" for blocked or no-proof cases) |
| `/case/[id]?send=n` (n = 1 to 3) | What exactly will I send? (slide-over drawer: engine draft, editable; WhatsApp / email / copy / PDF; nothing auto-sends). `/case/[id]/send/[stage]` shows the same panel as a page |
| `/case/[id]/pack` | Am I ready for the MSME ODR portal? (checklist, chronology, interest sheet, certificate **template**) |
| `/eligibility/[id]` | Does the law cover me? (shown instead of the case when the gate blocks) |

Judge console: **Ctrl+J**, the top-bar button, or `?judge=1`. Presets (Load always shows the clean preset), a live edit form covering the five rehearsed manipulations (dates, delivery proof, part-payments, Bank Rate override, investment/turnover, Udyam date with the Silpi test date), the engine's live result, a plain-language "changed from the preset" list and Reset. Each edit re-evaluates in about 350 ms locally, most of which is the 300 ms typing debounce.
The eligibility pill in the case header links every non-eligible state to its explanation panel (`/eligibility/[id]`).
URL params: `?view=supplier|cfo`, `?lang=en|kn`. The EN / ಕ toggle in the top bar sets `lang`. `kn.ts` covers the shell plus the owner-facing MVP set — timeline summary, readiness band and reasons headings, every ladder stage title and purpose, the top four engine warnings, and the eligibility pill labels (legal terms kept in English in brackets, every string marked `NEEDS-NATIVE-REVIEW`). Every other key falls back to English, so nothing renders blank. The Buyer CFO view stays English on purpose. `npm run i18n:check` proves the coverage and fallback rule; `docs/kannada-review.md` is the review sheet for a native speaker.
`?view=` also sets the persona tone: the supplier workspace is warm with a saffron accent, and the buyer CFO view is cooler with a slate-blue accent (`[data-tone]` in `app/globals.css`).

## Layout

```
app/                 routes (server pages read params, render client screens)
components/
  shell/             AppShell, Banners (offline/placeholder), PlaceholderBadge, JudgeConsole
  dues/ upload/ case/ send/ pack/ cfo/
  common/            Drawer (keyboard-trapped), StatusIcon (icon + text), Money, States, Icon
lib/
  api.ts             contract client + offline fallback
  useEvaluation.ts   one hook per case: resolve input, debounce, keep last good result
  format.ts          ₹ Indian grouping, dates, % (formatting only; BigInt paise for the live ticker)
  derive.ts          picks which engine value to show (never computes one)
  i18n/              en.ts holds every user-visible string; kn.ts covers the shell + owner-facing MVP set
  extraction.ts      upload review helpers over the contract ExtractionResponse
  useConnection.ts   engine live / offline pill
scripts/             sync-contracts.mjs, smoke.mjs
```

## Honesty rules this UI enforces

- A response carrying `PLACEHOLDER_DATA` shows a banner, and every money figure gets a "placeholder" badge.
- Unverified statute constants and citations are labelled "source not yet verified".
- The live interest ticker is `interest_outstanding + daily_accrual × elapsed time`, the only arithmetic in the browser (architecture §10).
- No "guaranteed" or "court-ready" wording. Drafts are labelled DRAFT. The certificate is a TEMPLATE.

Missing backend pieces and what the UI does meanwhile: see `CONTRACT-REQUESTS.md`.
