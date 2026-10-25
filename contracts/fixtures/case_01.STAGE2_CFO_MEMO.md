# DRAFT — case_01: note for the buyer's finance team

> **DRAFT** — prepared in SamadhaanOS from your case inputs and your case's own calculation.
> Nothing is sent from here: review it, edit it and approve it before you use it.
> Case case_01 · figures as on 2026-10-24

**To:** Finance team, Sample Buyer Corp (synthetic) (GSTIN 29SYN000000000Z1)

**From:** Sample Supplies Pvt Ltd (synthetic) · Udyam registration UDYAM-SYN-000000000

**Subject:** Our invoice dated 2026-02-16 — the balance as on 2026-10-24

A short note on where the supply under our invoice dated 2026-02-16 stands, and what the delay is costing your side. We would rather agree a date than argue one.

## Where things stand

| Where things stand | As on 2026-10-24 |
| --- | --- |
| Supply delivered | 2026-02-16 |
| Payment due | 2026-04-02 |
| Days past due | 205 |
| Outstanding principal | ₹12,50,000.00 |
| Interest so far | ₹1,20,394.51 |
| Total outstanding | ₹13,70,394.51 |
| Movement on this balance per day | ₹647.65 |

## What the delay is costing you

These are three separate lines. They are kept separate on purpose: they are different kinds of cost and are not added into one number.

### 1. Permanent loss — interest that is not deductible


| Line | Figure |
| --- | --- |
| Interest accrued and not deductible as on 2026-10-24 | ₹1,20,394.51 |
| Pre-tax equivalent of the rate used | 25.07% |
| Rate in force on 2026-10-24 | 17.25% a year (Bank Rate 5.75%) |

At this balance the outstanding figure moves by ₹647.65 a day.

### 2. Deferral — the tax timing effect at each year end

No qualifying 31 March checkpoint fell in this window with principal still unpaid, so this line reads nil as on 2026-10-24. That is an absence of a cost in this case, not a finding that deferral never applies. If a checkpoint appears, the inputs are cost of capital 12.00% and 1.00 year(s) deferred.

### 3. Disclosure — what the buyer's accounts carry

- s.22 disclosure: amounts payable to a micro or small enterprise must be disclosed in the buyer's audited accounts. *(wording not yet checked against a captured source — confirm it before relying on it)*
- No other gated points are switched on for this calculation, so none are listed here.

## What we would like to agree

We would like to agree a date for clearing the balance above. If a split suits your cash flow, say so and we will work to a schedule that does. A reply from your finance team is enough to start.

## Assumptions this draft was made under

- Every figure above comes from this case's calculation as on 2026-10-24; none of it is worked out in this draft.
- The three cost lines are shown separately and are never totalled into one number: what is lost permanently, what is deferred, and what must be disclosed are different things.
- The rate, the buyer tax rate and the cost of capital are the values in this case's inputs and statute config; where one is not yet verified against the statute sheet, the open points below say so.
- A written credit period of 90 days was supplied and is treated as a written agreement, such as a purchase order or a signed document. What counts as a written agreement is still open (OQ-5).
- days_overdue counts calendar days after the due date and stays empty until the appointed day; the appointed day is the due date plus one day (section 6.2).
- Part-payments follow PAYMENT_DATE_IS_REST_BOUNDARY: interest accrues to the payment date, is capitalised, the payment is applied, and the monthly rest cycle restarts from that date. The convention is shown on screen and is flagged for lawyer review (OQ-3).
- Rate mode FLOATING: the rate changes at each Bank Rate epoch boundary inside the delay, so a mid-delay change is split across rate segments (OQ-4).
- Appropriation mode INTEREST_FIRST changes only how a payment is split between principal and interest; the total balance is the same either way. The split feeds the 43B(h) base, it is not added to interest loss.
- rate_segments cover [from, to): `from` is the first day at that rate and `to` is the exclusive end, so segment days sum to the delay length.
- The three buyer-cost lines are reported separately and are never added into one number: what the buyer loses permanently, what it defers, and what it must disclose are different things.
- The interest figure is interest only. The s.43B(h) tax timing effect is reported on the deferral line and is never added to interest (trap 3).
- pretax_equivalent_rate_pct = statutory rate / (1 - buyer tax rate), rounded half-up to 0.01: 17.25 / (1 - 0.312) = 25.07.
- Each deferral checkpoint is a 31 March in [due_date, calculation_date] on or after section_43bh_first_fy; its cost is rounded to 0.01 first and the line total is their sum, matching the ledger's per-row rounding.
- Checkpoint figures use the request's cost_of_capital_pct and years_deferred as given; the engine does not pick those defaults.
- Deferral does not apply here because no qualifying 31 March checkpoint fell in the window with principal still unpaid.
- The expiry is the anchor date plus unknown year(s), where the anchor is the due date or, once one exists, the latest qualifying acknowledgment.
- Only a signed balance confirmation or a part-payment restarts the clock, and only when its date falls on or after the current anchor, so an older signature can never shorten the period the statute allows.
- Acknowledgments dated after the calculation date have not happened yet and are shown without restarting the clock.
- Bands are measured in calendar months from the calculation date: the expiry date itself is still in time, and the day after it reads EXPIRED.
- UNKNOWN means the inputs do not support a date, not that time remains.
- A row's status answers the argument from the engine's own verdicts only; whether a document is also in the request is reported separately as evidence held or missing, so the two columns can be checked independently.
- An arbitration clause and a set-off claim are always shown as an open question and are never decided here (OQ-7).
- Where the engine has no verdict - no gate result, no agreed period, or an unknown limitation band - the row reads as an open question rather than guessing in either direction.
- All seven rows are always returned, in the same order, so the panel can be compared between cases and the guidance card's first at-risk row is stable.
- The score starts at 100 and only loses points: it is 100 plus every reason's delta, clamped between 0 and 100, so adding up the reasons reproduces it exactly.
- With delivery proof missing the score is also capped at 50, which section 6.2 and 6.6 both call for. Its deduction is exactly 100 - 50, so the formula above still reproduces the capped number, and the reason says so in its own text rather than adjusting anything silently.
- The band comes from the gate, not from the score: a Silpi, trader or medium block sets BLOCKED and leaves the score where it is, which is why that reason carries a delta of zero.
- missing[] lists the evidence still needed for a complete pack. WhatsApp messages are treated as optional, so they are never deducted and never listed as missing.
- The next stage follows structural facts only - unresolved proof, a blocked gate, no due date yet, eligibility still open, evidence complete - with no day thresholds invented: Stage 1 to cure or wait, Stage 2 to resolve eligibility, Stage 3 to settle while paperwork is outstanding, Stage 4 when everything is held.

## Open points from this calculation

- Whether the Silpi works-contract test runs from the date of the contract or from the date of supply is still an open question (OQ-2, source V4). The config value silpi_test_date is null, so this check cannot decide. It is neither a pass nor a fail, and no silpi bar is being applied to this case.
- These promises to pay are recorded as potential acknowledgments but do not restart the limitation clock (2026-04-10). A promise in a chat thread is not a signed balance confirmation or a part-payment; only those two move the date shown here.
- The config has no limitation period, so no expiry date could be computed. The status below is UNKNOWN: this is an absence of a figure, not a finding that there is plenty of time left.
- Constant 'appropriation_mode_default' is not verified against the statute sheet (source 'open:section 5'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'bank_rate_epochs' is not verified against the statute sheet (source 'V1'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'credit_cap_days' is not verified against the statute sheet (source 'V2:s.15 proviso'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'day_count_fraction_days' is not verified against the statute sheet (source 'convention:section 5'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'gated_features' is not verified against the statute sheet (source 'V9'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'interest_multiplier' is not verified against the statute sheet (source 'V2:s.16'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'limitation_years' is null (source 'V7'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'objection_window_days' is not verified against the statute sheet (source 'V2:s.2(b)'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'payment_boundary_convention' is not verified against the statute sheet (source 'open:OQ-3'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'rate_mode_default' is not verified against the statute sheet (source 'open:OQ-4'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'silpi_test_date' is null (source 'V4'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'size_epochs' is not verified against the statute sheet (source 'V6'). Treat any number that depends on it as provisional until the statute sheet is captured.
- Constant 'trader_nic_prefixes' is not verified against the statute sheet (source 'V5'). Treat any number that depends on it as provisional until the statute sheet is captured.

---

*Not legal advice. This draft was generated by SamadhaanOS from the data entered for case_01 and the figures the engine returned as on 2026-10-24. It is decision support, not a lawyer's opinion, not a filing, and not a government form. Nothing is sent automatically: the owner reviews, edits and approves every draft.*
