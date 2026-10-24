# Open questions

Seeded from `architecture.md` section 13. Aniruddha resolves each against the
statute sheet. Rule per AGENTS.md §8: nothing here is fixed silently — the
engine runs on the documented default and surfaces `assumptions[]`/`warnings[]`.

| ID | Question | Default until resolved | Owner | Status |
|---|---|---|---|---|
| OQ-1 | Objection window: 15 days? Deemed acceptance anchored on delivery? | 15 and delivery, flagged | Aniruddha (V2) | open |
| OQ-2 | Silpi test date: contract or supply, and later supplies under an older contract | config null, gate returns `null` plus warning | Aniruddha (V4) | open |
| OQ-3 | Mid-period part-payment convention | payment date is a rest boundary, shown on screen | Aniruddha | open |
| OQ-4 | s.16 rate frozen at appointed day vs floating | FLOATING, toggleable | Aniruddha | open |
| OQ-5 | What counts as a "written agreement" (PO, email chain) | PO or signed document counts, assumption shown | Aniruddha | open |
| OQ-6 | Limitation period and acknowledgment rules | config null, status UNKNOWN | Aniruddha (V7) | open |
| OQ-7 | Arbitration clause and set-off interplay | `OPEN_QUESTION` row, never asserted | Aniruddha | open |
| OQ-8 | V9 buyer-pressure rules (GST credit reversal, MSME-1, appeal deposit) | gated off | Aniruddha | open |
| OQ-9 | Evaluation cadence, start time, video rules | per V11 | both | open |

## Contract v1.0 — interpretive choices (API agent)

Simplest-reading decisions taken while turning section 8 into Pydantic models.
These are contract/shape choices, not legal rules, so they are logged here for
review rather than routed to Aniruddha's legal queue. Changing any of them after
the `contract-v1` tag is an additive-only or human-approved change (section 9).

| # | Where the doc was loose | Choice made | Why simplest |
|---|---|---|---|
| CQ-1 | `config` endpoint response shape | Returns the raw statute-config dict, or a labelled `_stub` when the file is absent | Doc only says "config … with verified flags"; echoing the file is the least surprising |
| CQ-2 | `presets` list shape | `{"presets": [{"id", "title"}]}` | Doc says "list preset ids and titles"; a named array leaves room to add fields |
| CQ-3 | `presets/{id}` shape | `{"id", "title", "request"}`; `request` is the input-only case | Doc says "the preset's request (input only)"; wrapping keeps id/title for the UI |
| CQ-4 | Money/rate/percent type | `Decimal` in Python, `"0.00"` string in JSON/OpenAPI (`type: string`) | Matches "decimal strings" convention; avoids float in the legal path (§6) |
| CQ-5 | `rate_segments[].from` / `ledger[].from` | Field `from_` aliased to JSON key `from` | `from` is a Python keyword; alias keeps the contract key exactly as documented |
| CQ-6 | Nullable blocks in response | `timeline` / `financials` / `buyer_cost` are `T \| null`; rest are always present | Doc explicitly says "null if gate blocks/ineligible" for those three only |
| CQ-7 | Error shape on 422 and 404 | `{error: {code, message, field?}}`; 422 → `VALIDATION_ERROR`, 404 → `NOT_FOUND` | Section 8.1 defines the error envelope; codes follow the UPPER_SNAKE enum rule |
| CQ-8 | `contract_version` on request | Optional, defaults to `"1.0"` | Doc lists it as a field but not required; defaulting keeps hand-built requests valid |
| CQ-9 | `/evaluate-case` placeholder | Returns a fixed sample; echoes only `case_id` and `calculation_date` from the request | Neither echo is legal math; everything else is a labelled constant (golden rule 7) |

## New entries

Append below with: the rule, where it appears, what you believe is wrong or
missing, and what source would settle it.
