# UX and accessibility notes

Checked 2026-10-25 by the frontend agent, against CASE-01 and the shared shell.
The product is a decision-support tool, so the bar here is: a person who has not
seen it before can move through the case with a keyboard and understand what
each screen is telling them.

## How this was checked

- A DOM audit in Chrome at **1920×1080**, **1280×800** and **390×844**: every
  visible link, button, input, select and textarea; accessible names; label
  associations; heading levels; duplicate ids; broken `aria-labelledby` /
  `aria-describedby`; icon exposure; and text contrast on every text node.
- A keyboard pass: Tab through the page, open and close each drawer, check that
  focus stays inside and returns to the opener, and walk the custom controls.
- A validation pass over every `TextField` pattern in the judge console.
- Visual review of the four demo screens, the CFO view, evidence, math,
  escalation, dues, upload, pack and send pages at laptop and phone widths.

## What was fixed

| Area | Change |
|---|---|
| Keyboard | The rate-mode and appropriation toggles now follow the radio-group pattern: one tab stop, arrow keys (and Home/End) move and select, `aria-checked` follows the engine. |
| Drawers | Focus stays inside, Tab and Shift+Tab wrap, Esc closes, focus returns to the opener, and the page behind does not scroll. |
| Focus | A consistent 2px ring plus a light halo on every focusable control; no invisible tab stop in the sampled walks. |
| Colour | Selected persona/language/rate controls add weight and a raised surface, not just colour. Status is always icon + word. Link chevrons and meaningful “not fixed” / line-number text were darkened. |
| Contrast | Secondary ink is 4.98:1 on the canvas; field boundaries are 3.06:1; status text is 4.85–6.97:1; the CFO theme’s accent is 6.34–10.66:1. All text nodes passed 4.5:1 (3:1 for large text) in the audit. |
| Labels | Every input has a visible label or an accessible name. The two hidden file inputs are labelled and removed from the tab order; the visible button is the control. |
| Icons | SVG icons are decorative (`aria-hidden`); every icon-only button has an `aria-label`. |
| Headings | One h1 per screen, then h2 sections, then h3/h4 inside a card. “Rate segments” was an h3 before any h2 and is now an h2. |
| Validation | Required, date format, impossible calendar date (e.g. 31 Feb), whole days, amount, percent and crore each show a plain-language message tied to the field with `aria-describedby` and `aria-invalid`. |
| Responsive | No page-level horizontal overflow on ten routes at 1280px and 390px. The ledger and print pack scroll inside their own containers. |
| First-time use | A collapsed “New here? Read this page in three steps” explains the claim, the delivery-anchored clock and the next step. The `?demo=1` hint names the step and the next one. |

## Known gaps

- **No real screen-reader test.** The audit is DOM-based; NVDA, JAWS and
  VoiceOver were not run. This is the most important next check.
- **No automated a11y test in CI.** The Chrome audits used here were temporary
  scripts, not committed. Adding axe-core (or Playwright + axe) would make the
  checks repeatable.
- **Phone is read-only by decision.** Pages render without overflow at 390px,
  but the judge console and upload review are dense editing surfaces; use a
  laptop for edits.
- **Wide tables scroll.** The interest ledger and the print evidence pack keep
  their columns and scroll horizontally on a phone rather than becoming a
  card list.
- **Motion.** `prefers-reduced-motion` is honoured globally, but the recording
  setup was not tested with that setting; the live interest ticker is the only
  recurring animation.
- **Kannada.** The owner-facing MVP strings still need a native speaker’s
  review (`docs/kannada-review.md`); engine-provided sentences and the Buyer CFO
  view stay English.
- **Browser-native controls.** Range sliders and checkboxes use the platform
  appearance, so their size and focus rendering vary a little between Chrome,
  Firefox and Safari.
- **The connection pill is icon-only under the `sm` breakpoint.** Its state is
  still available to assistive technology and on hover, but a sighted phone
  user may need the colour and the warning triangle to read it.

## v4 audit (2026-10-25)

Scope: Dues from `GET /cases`, the choice card, `/case/[id]/early` in every track
state, the e-sign drawer, the recovery ladder and send drawer wiring, and the
judge demo controls. `docs/frontend-structure.md` does not exist, so the copy
rules used are the ones in `architecture_v4_two_options.md` section 10 and the
task: no "instant cash", "guaranteed", "bad cop", "shield" or "institutional
ledger"; no real bank, platform or provider names; no Aadhaar or government
styling.

How it was checked: a headless browser against a stand-in server walked the pages
above (dues; case with no track, financing and recovery tracks; the early page in
all eight states plus no track; the e-sign drawer; the judge console). For each
page a script measured text contrast against its effective background (AA:
4.5, or 3 for large text), listed unnamed controls, tabbed through up to 30 stops
checking for a visible focus ring, matched money against Indian grouping, and
searched the visible text for the forbidden words and a list of real names.

Result before fixes: no contrast failures, no unnamed controls, no focus stop
without a ring, every rupee amount in Indian grouping, no forbidden word or real
name. The failures below were found by reading the code and the rules.

### Fixed

- **DEMO badge missing where Option 1 appears.** Added a short "Demo" badge to the
  Dues track chip, to the case page's track strip ("Active option: Get paid
  early") and to the "recovery is locked" notice. The choice card column, every
  early step and the e-sign drawer already carried one.
- **A word that reads as a recommendation.** The recovery ladder and escalation
  tab labelled the engine's next stage "Recommended", which sits right under the
  two-option card and could read as advice to take Option 2. It now says "Next
  step" (English and Kannada). The e-sign "best"/"recommend" scan is clean.
- **Numbers typed into copy or code.** The e-sign hint named the demo code
  (123456) and the digit count, the live-update line said "every 3 seconds", the
  scenario list said "3 times", and the e-sign modal counted attempts from a
  constant of 3. The code is no longer shown, the digit count and polling
  interval come from constants, and attempts left come only from the server's
  `attempts_left` (in the session or the refused-code error details). Until the
  server sends it, the modal says only that attempts are limited.
- **Status by colour alone.** The refused-code message in the e-sign drawer was
  red text only; it now has a warning icon. (Every status pill already carried an
  icon and a word.)
- **The stepper was a bare list.** It now has a name, each step reads "Step n of
  6" to a screen reader, and a polite live line announces which step the server
  says is current (or where it stopped) without moving focus.

### Checked and left as is

- Keyboard order on the early page is header, "Back to the case", then the
  controls of the current step only; later steps hold nothing focusable until the
  server reaches them. The e-sign drawer keeps focus inside after 30 Tab presses
  and closes on Escape.
- "TReDS" and "RBI Bank Rate" stay: the first is the scheme the product is about,
  the second a statutory term, not a company or platform brand. Bank rate
  figures come from the engine.
- "No Aadhaar number is collected or stored" is the required disclaimer, so a scan
  for "Aadhaar" will always find it.

### Known gaps

- The v4 strings are English only; the Kannada dictionary falls back to English
  for them. Server-supplied notes and reasons on the options and early screens are
  shown as the server sends them.
- The Dues "Paid early (simulated)" figure sums invoice amounts in the browser
  (exact paise). It should come from the server.
- Contrast was measured with computed colours for light mode only.
- Everything above was run against a stand-in server, not the real backend.

## v5 audit (customer book, payments, import, insight cards)

Done 2026-10-26 by reading the code, searching the dictionary and components,
computing contrast from the colour tokens, and running typecheck, lint, the
language check and the build. It was **not** run in a browser, with a screen
reader, or against a seeded v1.2 server, so the keyboard and focus items below
are checked from the markup, not by tabbing through the screens.

**Checked and fine**

- Banned words (score, rating, risky, bad payer, defaulter, blacklist, merge for
  groups): none in any v5 string or component. Remaining hits in `en.ts`
  (`defense.AT_RISK`, the evidence "score" and readiness gauge) belong to the
  evidence-readiness feature of a single invoice, not to a buyer.
- Averages: the Dues strip, each customer row, the profile tiles and the
  portfolio cards all print "based on N" next to the average, and below the
  minimum history they print "Not enough history" instead of a number.
- Charts: the payment-history chart has a text summary above it and a
  chart/table toggle; the concentration bar has a visible list and a
  screen-reader sentence; the cash-in bars have a summary line and an amounts
  list.
- Text contrast (computed): ink-500 on white 5.35, on paper 4.98, on paper-sunk
  4.73; warn on white 5.67; block on white 6.57; info on its wash 6.97; ok on
  its wash 4.85; saffron-600 on white 4.98. All at or above 4.5. Focus uses the
  global 2px ring.
- Numbers go through `lib/format.ts` (`money`, `count`, `pct`, `date`,
  `approxDays`); no `toFixed`, `toLocaleString` or `Intl` in v5 code.

**Fixed in this audit**

1. `book.own_data_only` said "scored or predicted" (banned words, and untrue
   beside the labelled cash-in estimate). Now "Nothing is shared with anyone."
2. The Dues "largest customer's share" card showed the server's
   `concentration_note`, which says "not a risk score". It now shows a fixed
   plain line; the server note is not displayed anywhere.
3. The profile's "not enough history" note used the server's sentence, which
   carries its own numbers and may be a raw code. It now uses the dictionary
   string with N and the minimum.
4. Terms-check card: an average with no sample size is not shown in the compact
   row; the full card says "Sample size not sent" instead of leaving N out.
5. "Before 31 March" card had the date typed as a fallback. The title now comes
   from the server's date, or "Before the financial year ends" when there is none.
6. The import "5 MB" limit was typed into two strings; both now take it from the
   one constant.
7. Non-text contrast: the concentration segments (down to 1.8:1), the "others"
   segment (1.4:1) and the cash-in bars (2.7:1) were below 3:1. Segments now run
   from 100% to 50% ink (3.6:1 or better), "others" is hatched, bars are 60% ink.
8. The profile invoices table and the chart's table view scroll sideways but
   could not take keyboard focus. Both are now focusable labelled regions.
9. The similarity percent was worked out inside a component; it now lives in
   `lib/format.ts` (`ratioPct`).
10. Insight figures were truncated with an ellipsis in narrow cards, hiding
    digits. They now wrap.

**Known gaps**

- Not tabbed through in a browser: dashboard, profile, then case. Everything on
  that path is a link, button or select, and the group rows are buttons, but the
  focus order has not been observed.
- `DEFAULT_MIN_HISTORY = 3` in `lib/useCustomer.ts` is used only when the server
  omits `min_history`; it is the documented default, a product setting.
- "43B(h)" and "31 March" in the before-March card come from the brief and the
  server's note; the date is the server's. The 43B(h) wording should be checked
  against the statute sheet by Aniruddha.
- The Kannada dictionary has none of the v5 strings; they fall back to English.
- Dark mode is not part of this product; persona tones were not re-measured.

## Re-running the check

```bash
cd frontend
npm run dev            # in one terminal
npm run check          # typecheck, lint, build
npm run smoke          # routes, demo links, fixtures, language toggle
```

Then, in the browser: Tab through CASE-01; open the ledger, assumptions,
defenses and judge drawers with Enter and close with Esc; use arrow keys on the
rate-mode control; submit an empty and a 31-Feb date in the judge console; and
view the case at 1280px and 390px wide.
