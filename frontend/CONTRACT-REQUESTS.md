# Contract and backend requests from the frontend

Written by the frontend (Mochi's side). The frontend does not edit `backend/`,
`contracts/` or the `Makefile`; this file is the handoff. Every item says what
the UI does **today** without it, so nothing here blocks the demo, and the UI
picks the real thing up automatically after a `git pull` (the
`sync-contracts` script re-copies `contracts/types.ts` and fixtures on every
`npm install`, `npm run dev` and `npm run build`).

Status key: **open** = not done yet. Mark items **done** in the backend commit that resolves them.

| ID | Request | Why the UI needs it | What the UI does meanwhile | Status |
|---|---|---|---|---|
| CR-1 | Optional guidance hints on `CaseEvaluationResponse`, for example `guidance: { stage, action_code, top_defense_id } \| null` (additive, contract 1.1) | Spec F10: the guidance card shows one action and the top defense for the current stage | Uses `evidence_readiness.recommended_stage` for the stage and picks the first `AT_RISK`, then `OPEN_QUESTION`, then any defense. Action text comes from i18n by stage number | open |
| CR-2 | `GRN` in `EvidenceKind`, and warning code `GRN_MISSING_DEEMED_ACCEPTANCE` (prompt B3a) | Spec C2: the deemed-acceptance line must show whenever the GRN is missing | Shows the line when `timeline.objection_status == DEEMED_ACCEPTANCE`, and already listens for `GRN_MISSING_DEEMED_ACCEPTANCE` in `warnings[]` | open |
| CR-3 | `ReadinessBand.COURT_READY` → `EVIDENCE_COMPLETE` (spec changelog #19). This is a rename, so both humans must agree (architecture §9.3) | "Court-ready" is a legal-conclusion claim | The UI never prints the code. Both names map to "Evidence looks complete based on what you entered" | open |
| CR-4 | `POST /api/v1/extract-evidence` (B9-lite) in the contract: multipart field `file`; response `{ fields: { <key>: { value, source_text, page, method: "regex"\|"llm"\|"missing", confidence } }, supplier_name? }`; field keys `invoice_number, invoice_date, amount, supplier_gstin, buyer_gstin, buyer_name, delivery_date, po_reference`; dates `YYYY-MM-DD`, amount a decimal string | Upload and review screen (F12) | Mirrors this shape in `lib/extraction.ts`. On 404/405/5xx it shows a sample extraction labelled placeholder (`demo-cases/invoice_sample.extraction.json`) | open |
| CR-5 | `POST /api/v1/generate-artifact` (B8): `{ kind, request }` → `{ filename, markdown, pdf_base64? }` with kinds `STAGE1_BALANCE_CONFIRMATION`, `STAGE2_CFO_MEMO`, `STAGE3_SETTLEMENT_TERMSHEET`, `STAGE4_EVIDENCE_PACK` | Send drawer (F11) and evidence pack | On 404 it shows a frontend draft filled only with engine numbers and request inputs, labelled "Placeholder draft". The evidence pack downloads through browser print | open |
| CR-6 | A catch-all exception handler so unexpected 500s also use the `{error:{code,message}}` envelope | The UI treats a 5xx **without** the envelope as "backend unreachable" (that is what the dev proxy returns when FastAPI is down) and switches to offline mode | A real engine crash currently shows as "Offline demo data" instead of an error | open |
| CR-7 | Presets `case_02` … `case_05` (B7) | Dues list and judge console | Uses `demo-cases/demo_02` and `demo_03` (synthetic **inputs** only, mirroring spec CASE-02/03). When real presets land, the demo files can be deleted. Their ids do not collide with `case_*` | open |
| CR-8 | Bank-rate epochs before 2026-04-01 (V1), or preset calculation dates inside the covered epochs | `case_01` (delivery Dec 2025) and the demo cases (Jan 2026) start their delay before the first configured epoch, so `bank_rate_on` will raise `NoEpochFound` once the real engine runs (architecture §12 trap 1) | The UI shows the engine's error message and keeps the last good result | open |
| CR-9 | Buyer grouping by PAN (B11), or portfolio totals per buyer group | Dues summary ("total overdue across buyers") | No cross-buyer totals are shown, because adding money in the browser would be legal math (golden rule 6). It shows counts only, with a note | open |
| CR-10 | `POST /api/v1/simulate-settlement` | Stage 3 settlement numbers | Not used yet; the Stage 3 draft does not show split numbers | open |

## Notes for running together

- No CORS change is needed. The frontend proxies `/api/v1/*` to `BACKEND_URL`
  (default `http://127.0.0.1:8000`; see `next.config.ts`).
- Fixtures come from `contracts/fixtures/` and are never edited on the frontend.
  Regenerate them with `make contract-fixtures` / `make fixtures` on the backend side.
