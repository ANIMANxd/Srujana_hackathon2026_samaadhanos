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
