# Test oracles: the spec suite's hand calculations and findings

Written by the **test author** (AGENTS.md section 3). Sources: `docs/architecture.md`,
`docs/open-questions.md`, `docs/statute-sheet/CHECKLIST.md`, the statute config
(read through `backend/app/config_loader.py`), and the public HTTP interface
(`POST /api/v1/evaluate-case`). **`backend/engine/**` was not opened.**

Method:

- round numbers throughout - principal `365000.00` divides the 365-day day
  count exactly (1000/day), so hand interest lands on whole rupees;
- the statutory rate is always `interest_multiplier x Bank Rate`, both read
  from the config (today `3 x 5.50 = 16.50%` to 2026-10-07, `3 x 5.75 = 17.25%`
  after; V1 uncaptured, so every run carries `UNVERIFIED_CONSTANT` warnings);
- rounding is half-up to `0.01` at each row (architecture 6.3);
- every expectation is either an arithmetic sum shown below or a rule quoted
  from a named section. Failures are findings; they are not weakened away.

Re-run: `python -m pytest backend/tests/spec -q`.

---

## 1. The oracles (hand calculations)

### 1.1 Acceptance and due dates (`test_s2_acceptance_dates.py`, architecture 6.2)

Rules: acceptance anchors on **delivery**; window end = delivery +
`objection_window_days`; due = acceptance + applied days; appointed = due + 1.

| Scenario | Calculation | Expected |
|---|---|---|
| Delivery 2026-03-20, invoice 2026-03-16 | 2026-03-20 + 15 (no agreement) | window end 2026-04-04, due 2026-04-04, appointed 2026-04-05; invoice date irrelevant |
| Objection on the last window day (delivery 2026-05-10, raised 2026-05-25, resolved 2026-05-26) | acceptance 2026-05-26 + 15 | due 2026-06-10, appointed 2026-06-11, no late complaint |
| Raised one day late (2026-05-26) | window closed 2026-05-25 | acceptance stays 2026-05-10, due 2026-05-25, recorded in `late_complaints` |
| Unwritten objection (2026-05-15) | not written | acceptance stays on delivery, recorded |
| Unwritten objection left open | acceptance undecidable | `PENDING_RESOLUTION`, null money, warning present (CQ-11) |
| Delivery 2026-06-01, no terms | `no_agreement_days` = 15 | due 2026-06-16, appointed 2026-06-17 |
| Delivery 2026-06-01, Net 90 | agreed 90, `credit_cap_days` = 45 | applied 45, `clamped` true, due 2026-07-16, appointed 2026-07-17 |
| Delivery 2026-06-01, Net 30 | agreed 30 (< 45) | applied 30, due 2026-07-01, appointed 2026-07-02 |

Open rules asserted here: OQ-1 (the window comes from config and the config
value is unverified, so a warning must name `objection_window_days`), OQ-5
(Net 90 assumes a written agreement and says so).

### 1.2 The interest ledger (`test_s3_interest_ledger.py`, architecture 6.3)

**Leap-year rest (delivery 2028-01-15, calc 2028-03-01, rate 17.25%):**
rest 1 = 2028-01-31 + 1 month = **2028-02-29** (leap February clamped);
29 days: `365000 x 17.25% x 29/365 = 5002.50`; balance 370002.50; 1 day stub:
`370002.50 x 17.25% x 1/365 = 174.864... -> 174.86`; interest **5177.36**;
claim **370177.36**.

**Payment on a rest day, evaluated later (payment 2026-06-27, calc 2026-07-05):**
31 days to the rest: `365000 x 16.50% x 31/365 = 5115.00`; payment 100000 with
INTEREST_FIRST clears 5115.00 interest then 94885.00 principal -> principal
**270115.00**; stub 8 days from the rest: `270115.00 x 16.50% x 8/365 =
976.85`; interest outstanding **976.85**, claim **271091.85**. (Passes.)

**Same payment, evaluated on the rest day itself:** same accrual 5115.00, and
6.3 requires the payment to be applied (accrue -> capitalise -> apply ->
restart) -> principal **270115.00**, interest outstanding **0.00**. (**Finding F5.**)

**Payment before the appointed day (payment 100000 on 2026-07-05, calc
2026-07-10, appointed 2026-07-17):** no delay yet -> interest **0.00**,
principal **265000.00**, claim **265000.00**, payment visible in the rows.

**Two payments before the appointed day (100000 + 50000, calc 2026-07-15):**
interest **0.00**, principal **215000.00**, both payments booked.

**Payment larger than the balance (payment 500000 on 2026-06-20, calc
2026-06-27):** 3 days to the payment: `365000 x 16.50% x 3/365 = 495.00`;
claim at that moment 365495.00, so **365495.00 is applied** (not 500000 - CQ-17),
the excess 134505.00 goes into the `OVERPAYMENT` warning, principal/interest
outstanding **0.00**, interest total **495.00**.

**Bank-rate change mid-delay (delivery 2026-09-16, appointed 2026-10-02, rest
2026-11-02, calc 2026-11-11):** boundary 2026-10-07.

- FLOATING: 5 days at 16.50% + 26 days at 17.25% =
  `365000 x (0.165x5 + 0.1725x26)/365 = 5310.00`; balance 370310.00; 9 days at
  17.25%: `370310.00 x 0.1725 x 9/365 = 1575.086... -> 1575.09`; interest
  **6885.09**, claim **371885.09**; segments show both rates and break on
  2026-10-07.
- FROZEN_AT_APPOINTED_DAY: whole period at 16.50%: 31 days `= 5115.00`;
  balance 370115.00; 9 days `370115.00 x 0.165 x 9/365 = 1505.8103... ->
  1505.81`; interest **6620.81**, claim **371620.81**; every segment reads 16.50.

**Appointed day on the epoch date (delivery 2026-09-21, appointed 2026-10-07):**
the day an epoch starts carries the new rate (5.75 -> 17.25%); 13 days:
`365000 x 17.25% x 13/365 = 2242.50`; claim **367242.50**.

Open rules asserted here: OQ-4 (FLOATING default named in the assumptions) and
OQ-3 (`PAYMENT_DATE_IS_REST_BOUNDARY` stated whenever a payment exists).

### 1.3 The gate (`test_s4_gate_blocks.py`, architecture 6.1)

| Scenario | Expectation | Source |
|---|---|---|
| investment 26 cr (small ceiling 25 + 1) | `EXCLUDED_MEDIUM`, money null, BLOCK warning, `alternative_remedy` | 6.1 + config `size_epochs` |
| investment 24 cr, turnover 5 cr (fits SMALL) | **not** `EXCLUDED_MEDIUM` | 6.1: "Medium and above fail" - **Finding F6** |
| NIC built from a configured prefix (`45/46/47` + `100`) | `EXCLUDED_TRADER`, money null | 6.1 + config `trader_nic_prefixes` |
| `silpi_test_date` null (shipped config) | check `null`, `OPEN_QUESTION` warning, `INSUFFICIENT_DATA` | 6.1 + OQ-2 (**passes**) |
| override SUPPLY + Udyam registered after the supply | `BARRED_SILPI` | 6.1 + section 11 "Silpi blocks" - **Finding F7** |

### 1.4 Limitation (`test_s5_limitation.py`, architecture 6.5)

Config `limitation_years` is null -> expiry `null`, status `UNKNOWN`, and a
warning naming `limitation_years` (architecture 5). Acknowledgment flags:
signed balance confirmation -> `restarts_clock` **true**; part-payment (signed)
-> **true**; WhatsApp promise -> **false**; a confirmation that is not signed
-> **false** (6.5 requires `is_signed` *and* a qualifying kind).

### 1.5 Buyer cost (`test_s6_buyer_cost.py`, architecture 6.4)

Delivery 2026-04-10 -> appointed 2026-04-26; payment 100000 on 2026-05-10:
14 days `365000 x 16.50% x 14/365 = 2310.00`, so INTEREST_FIRST sends 2310.00
to interest and 97690.00 to principal -> principal **267310.00**. Checkpoint
2027-03-31 (inside [due 2026-04-25, calc 2027-04-10], FY 2026-27 on/after
`section_43bh_first_fy` = 2023-24):

- unpaid principal = **267310.00**
- tax timing effect = `267310.00 x 30% = 80193.00`
- deferral cost = `80193.00 x 12% x 1.00 = 9623.16`

Plus: the three lines are reported separately, the s.22 disclosure line exists,
`other_pressure_points` is empty (OQ-8 gated off) and `gated_features` is
named in an unverified-constant warning.

### 1.6 Invariants (`test_invariants.py`)

1. rows balance (`opening + interest - payment = closing`, CQ-17) and sum to
   `interest_total` (section 11); with no payment, claim = principal + interest;
2. `total_claim` and `interest_total` identical under INTEREST_FIRST and
   PRINCIPAL_FIRST, while the buckets differ (6.3);
3. interest is non-decreasing across calc dates 2026-06-10 < 06-17 < 06-27;
4. the total claim never falls as the calc date moves forward;
5. 730000.00 principal never yields less interest than 365000.00;
6. the same request twice is byte-identical (no clock, no randomness);
7. reversed `part_payments` and reversed `objections` give identical output.

### 1.7 Malformed input (`test_malformed_inputs.py`, architecture 8.1)

Each must be 400 or 422 with `{error: {code, message}}` and no traceback:
negative principal, calculation date before delivery, duplicate payments,
impossible dates (`2026-02-30`, `2026-13-01`), negative `written_credit_days`,
negative `years_deferred`.

---

## 2. Findings (failing tests, kept failing)

Seven tests fail against the current engine/API. Each is left failing on
purpose; nothing was weakened to make it pass.

### F1 - MAJOR - a payment on the rest day is silently dropped
- **Test:** `test_s3_interest_ledger.py::test_payment_on_the_rest_day_that_is_also_the_calculation_date`
- **Expected (6.3, OQ-3):** payment 100000 dated 2026-06-27 (the rest day,
  also the calc day) applies: principal **270115.00**, interest outstanding
  **0.00**, ledger books 100000.00.
- **Actual:** the ledger shows one `REST` row with `payment: 0.00`;
  principal stays **365000.00**, interest outstanding **5115.00**, claim
  **370115.00** - the money the buyer paid is missing and the claim is
  overstated by 100000.00.
- **Scope:** with the calculation date moved to 2026-07-05 the same rest-day
  payment *is* applied (separate passing test), so the collision is specific to
  payment = rest day = calculation date; a payment on the calc day that is not
  a rest also applies.
- **What would settle it:** architecture 6.3's own words (accrue to the payment
  date, capitalise, apply, restart) plus OQ-3's convention; no statute needed.

### F2 - MAJOR - the enterprise class comes from the claim, not from the figures
- **Test:** `test_s4_gate_blocks.py::test_a_supplier_inside_the_ceiling_is_not_excluded_as_medium`
- **Expected (6.1):** the class is "looked up in `size_epochs`" on the supply
  date; investment 24 cr and turnover 5 cr sit **inside** the configured small
  ceilings (25/100) -> small, not medium -> not excluded.
- **Actual:** `EXCLUDED_MEDIUM`; the check detail says it measured against the
  **micro** ceilings (2.5/10) and that "investment 24 crore exceeds 2.5 crore".
  Probes through the public interface show the deciding input is the request's
  `supplier.enterprise_class`: claiming SMALL with the same figures passes,
  claiming MICRO with 9 cr fails. So a supplier whose figures fit SMALL can be
  excluded as "medium", and the status name contradicts the figures.
- **What would settle it:** architecture 6.1's wording (class looked up from
  `size_epochs`; "Medium and above fail") and the V6 capture of the real
  investment/turnover limits.

### F3 - MAJOR - the Silpi block is unreachable
- **Test:** `test_s4_gate_blocks.py::test_silpi_block_when_the_udyam_date_falls_after_the_test_date`
- **Expected (6.1 + section 11, which lists "Silpi blocks" as an edge case):**
  with `silpi_test_date = SUPPLY` and the Udyam registration dated after the
  supply, the chronology check fails -> `BARRED_SILPI`.
- **Actual:** `passed: true` and `ELIGIBLE`; the detail reads "the config runs
  the test from the supply (2026-06-01), and that date is present" - i.e. the
  check only confirms the configured date exists. Probes show it passes for
  registration before *and* after the date, and under the CONTRACT anchor too,
  so the check never compares dates and `BARRED_SILPI` is unreachable.
- **What would settle it:** the V4 capture (the works-contract/Silpi rule and
  its direction); OQ-2 currently asks only *which* date anchors the test, not
  what the comparison is.

### F4 - MAJOR - duplicate payments are accepted and double-counted
- **Test:** `test_malformed_inputs.py::test_duplicate_payments_are_refused`
- **Expected:** a clean 400/422 refusal (this suite's brief; 8.1's error model).
- **Actual:** 200; both entries are booked (two 50000.00 rows, principal
  365000 -> 265000), so the same payment is counted twice.
- **What would settle it:** a product decision on whether identical
  date+amount+reference rows are one payment or two, then validation in the
  request schema. No statute is involved; the risk is a wrong claim figure.

### F5 - MAJOR - a negative credit period produces a due date before delivery
- **Test:** `test_malformed_inputs.py::test_other_impossible_values_are_refused`
- **Expected:** 400/422 (a credit period cannot be negative).
- **Actual:** 200 with `written_credit_days = -20` -> applied 20 days,
  **due 2026-05-12** for a delivery on **2026-06-01**, appointed 2026-05-13,
  `days_overdue` 46 - the clock runs from before the goods arrived, which
  would misstate delay, interest days and any limitation date downstream.
- **What would settle it:** architecture 6.2 (due = acceptance + applied days,
  where acceptance cannot precede delivery) and V2 for the range of accepted
  credit periods.

### F6 - MINOR - a calculation date before delivery is accepted silently
- **Test:** `test_malformed_inputs.py::test_calculation_date_before_delivery_is_refused`
- **Expected:** 400 `RULE_VIOLATION` (8.1: 400 for rule violations; this
  suite's brief lists it as malformed).
- **Actual:** 200 with a safe degradation - empty ledger, `days_overdue` null,
  claim = principal, `NO_DELAY_PRICED` warning. Nothing nonsensical is
  computed, but no refusal happens either.
- **What would settle it:** deciding in the error model whether "no delay
  priced" is a warning (current behaviour) or a rule violation.

### F7 - MINOR - `late_complaints` mirrors the request's array order
- **Test:** `test_invariants.py::test_shuffling_objections_does_not_change_the_output`
- **Expected (this suite's brief):** shuffling input lists changes nothing.
- **Actual:** every computed value is identical (acceptance, due, appointed,
  `days_overdue`), but the `late_complaints` list comes back in request order,
  so the response object differs. Payments shuffle cleanly; objections do not.
- **What would settle it:** a decision that `late_complaints` is sorted by date
  (or documented as input-ordered) in architecture 6.2.

---

## 3. Oracle corrections made while writing (not findings)

Recorded so a reader can tell an engine bug from a test bug:

1. **Two-payments scenario:** the first draft set the calculation date
   (2026-07-20) *after* the appointed day (2026-07-17) and still expected zero
   interest. The engine correctly returned 291.58
   (`215000 x 16.50% x 3/365`). The scenario now calculates on 2026-07-15,
   before the appointed day, where 0.00 is the documented answer.
2. **Ledger chain assumption:** the first draft required the rows' *dates* to
   abut. Nothing in the architecture promises that (a payment inside a stretch
   where no interest can accrue leaves a date gap with no row), so the helper
   now asserts the documented properties: each row balances, the balance
   carries from one row's closing to the next row's opening, and the rows sum
   to `interest_total`.

## 4. What passes

39 of 46 spec cases pass, including every money oracle above (leap-year rest,
both rate modes, epoch boundary, overpayment, pre-appointed payments, the
buyer-cost checkpoint), the acceptance/boundary dates, the trader and medium
blocks, the OQ-2/OQ-6/OQ-8 defaults with their warnings, five of the seven
invariants, and four of the malformed-input cases (negative principal,
impossible dates, negative `years_deferred` are refused today).

The statute sheet has captured nothing yet (V1-V11 all `no`), so every
constant these tests rely on is unverified by construction; the suite asserts
that the warnings say so rather than trusting the numbers silently.
