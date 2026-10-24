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
| CQ-10 | `days_overdue` counting (6.2 says only "vs calculation_date, null if not yet appointed") | Counts calendar days after `due_date`, starting at 1 on the appointed day; null while `calculation_date < appointed_day` | Appointed day is due date + 1, so "days overdue" runs from the due date; this makes the value start at 1 rather than 0 on the first overdue day and never show 0 |
| CQ-11 | Several qualifying objections, 6.2 describes one | Acceptance is the **latest** `resolved_date`; any one still unresolved leaves acceptance null with a `PENDING_RESOLUTION` warning | The clock cannot resume until the last objection inside the window clears; guessing an earlier date would understate the delay |
| CQ-12 | What `invoice_date` is for in 6.2 | Accepted as an input, never used to anchor anything; kept in the signature so "anchor on delivery" is testable rather than prose | Section 7 makes delivery the anchor, so the invoice date must demonstrably not move the clock |
| CQ-13 | `rate_segments` endpoints (6.3 says "splits at epoch boundaries" but not inclusive/exclusive) | Half-open `[from, to)`: `from` is the first day at that rate, `to` is the exclusive end | Consecutive segments then abut without double-counting a day and their days sum exactly to the delay length |
| CQ-14 | A ledger row whose span crosses a rate change (6.3 defines rows by rest/payment/stub, never by rate) | One row per accrual period; interest = opening x sum(rate x days) / day_count, `rate_pct` shows the rate at the row start, a note flags the change, and `rate_segments` carries the exact split | Keeps rows period-based as 6.3 describes, so compounding still happens only at rests and payments; splitting rows at a rate boundary would compound an extra time mid-period, which the spec does not describe |
| CQ-15 | `interest_total` vs `interest_outstanding` when a payment clears the claim | `interest_total` = sum of the rows (accrued); `interest_outstanding` = the interest bucket after appropriation. They differ only when a payment absorbs interest | The task requires totals to equal the sum of rows, and the schema carries both fields, so both are reported rather than silently reconciled |
| CQ-16 | Interest runs from after the appointed day, so a delay can show N+1 days overdue but N interest days | Interest periods are `(appointed_day, ...]` because 6.3 puts rests at `appointed_day + k months`; `days_overdue` counts from `due_date = appointed_day - 1` | 6.2 sets appointed = due + 1 and 6.3 starts rests there, so the one-day gap is the appointed day itself: past due, but not yet interest-bearing |
| CQ-17 | What an overpayment row puts in `payment` | The amount actually applied to the claim; the requested amount and the excess go in the `OVERPAYMENT` warning | Keeps `opening + interest - payment = closing` exact so the printed ledger still sums |
| CQ-18 | `POST /simulate-settlement` is listed in 8.1 but 8.3 defines no response schema for it | `SettlementResult` stays engine-local: total_claim, interest_waived, interest_paid, principal_paid, total_payable, payments[{kind, days_from_now, amount}], net_recovery, the echoed inputs, assumptions | Nothing is pre-empted for the contract; the API agent adds it additively through section 9 once the shape is agreed |
| CQ-19 | What `waiver_pct` and `upfront_pct` apply to (the task names both, not their bases) | Waiver applies to outstanding interest only; upfront applies to the amount payable after the waiver | The task asks for "interest waived and paid", so the lever is interest, and waiving principal would write off the price of goods actually delivered |
| CQ-20 | Whether `days_to_second_payment` discounts the recovery | No: `net_recovery` is nominal rupees and the day count only says when cash arrives | The task asks for plain arithmetic only; discounting would need a rate, which is a rule this module deliberately does not read |
| CQ-21 | Per-checkpoint deferral cost has no field in 8.3's `DeferralCheckpoint` | Rounded to 0.01 per checkpoint inside the engine, only the sum exposed as `deferral_cost` | The contract carries one `deferral_cost`; rounding each checkpoint first keeps that total equal to the sum of its rows |
| CQ-22 | Which day's statutory rate feeds `pretax_equivalent_rate_pct` when FLOATING splits the delay (6.4 says only "statutory_rate") | Taken as an explicit `statutory_rate_pct` input, which `evaluate.py` supplies from the active rate mode | buyer_cost must not reach into rate-mode logic it does not own; keeping it an input leaves the caller's choice visible instead of deciding it silently here |
| CQ-23 | The task names the readiness band `EVIDENCE_COMPLETE`; the frozen contract still carries the old name | Engine emits `EVIDENCE_COMPLETE`. The contract member is **CR-3**, a rename that needs both humans (9.3), so `schemas.py` and `contracts/` were left untouched | The task forbids the old wording in code, text and comments, and the spec renamed it (changelog #19). Contract tests still pass because they validate fixtures, and readiness is not wired into `/evaluate-case` yet; the UI already has an i18n key for the new value |
| CQ-24 | Whether a gate block should also lower the readiness score | No: the `GATE_BLOCKED` reason carries delta 0 and only sets the band | The task ties Silpi/trader/medium blocks to the **band**, and the score means evidence readiness; a zero delta keeps `score = base + sum(deltas)` true while still explaining BLOCKED on screen |
| CQ-25 | Whether `EXPIRED` applies on the expiry date itself | `EXPIRED` only after it; the expiry day still reads `WARN_6M` | The other reading would declare the claim out of time on the last day it is arguably still in, which asserts a contested position the engine should not make |
| CQ-26 | Whether missing evidence should change a defense's status | No: status comes from the gate/acceptance/agreement/limitation verdicts alone; `evidence_have`/`evidence_missing` are reported beside it. Which kinds each row weighs is fixed in `_ROW_SPECS` | Keeps the two columns independently checkable; folding paperwork into the verdict would hide whether the strength came from a rule or from a document |
| CQ-27 | Whether an acknowledgment dated before the due date can restart the clock (6.5 says only "restarted by") | Restarting only ever moves the anchor forward, so a pre-due-date signature never shortens the window | Pulling the expiry back by an old signature could declare an expired claim alive on a date no rule supports |
| CQ-28 | Whether a missing due date should also give `UNKNOWN` (6.5 names only a null period) | Yes: no due date means no anchor, so `UNKNOWN` plus `NO_DUE_DATE` | The alternative is an `OK` band with no expiry, which reads as plenty of time left when nothing was computed |
| CQ-29 | The readiness scoring constants: base 100, the deduction table (40/15/15/10/5/10/10), the 50 cap, and treating WhatsApp evidence as optional | Treated as presentation conventions, stated in `assumptions[]`; the delivery deduction is derived as base minus the cap so the formula still reproduces the score | None of these is a statutory figure, and the cap plus optional-chat choices come from 6.2/6.6 needing *some* value; the derivation keeps them explainable rather than magic |
| CQ-30 | How `recommended_stage` is derived (6.6 says only "recommended stage") | Structural ladder, no day thresholds: no proof / blocked gate / no due date -> 1, eligibility unresolved -> 2, everything held -> 4, otherwise 3 | A threshold table would invent escalation timing that no document gives; each branch rests on a documented prerequisite instead (6.2 pins Stage 1 for missing delivery proof) |
| CQ-31 | The shape of `rule_ref` and the defense ids (8.3 says a `rules.<code>.title` key but not the code) | Ids in the order 6.6 lists the arguments; `rule_ref` = `defenses.<id>` so the key is `rules.defenses.<id>.title`, matching the engine's existing `gate.<check>` pattern | The frontend has no `rules.*` keys yet, so this is the moment to fix one shape for every module rather than three |

## New entries

Append below with: the rule, where it appears, what you believe is wrong or
missing, and what source would settle it.
