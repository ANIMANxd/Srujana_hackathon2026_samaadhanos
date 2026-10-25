# Kannada review sheet

Status: **draft, not reviewed**. Every string below needs a native Kannada
speaker's check before it is shown to a real supplier. English is the source of
truth; the Kannada must not add a promise, a legal conclusion or a number the
English does not have.

Generated from `frontend/lib/i18n/en.ts` and `frontend/lib/i18n/kn.ts` by
`npm run i18n:doc`. Re-run after any string change; keep reviewer notes in a
separate copy or in the review issue, not in this generated file.

## How to review

1. Read the English source and the Kannada draft together. Flag anything that
   sounds like legal advice, a guarantee, or a stronger claim than the English.
2. Legal terms are deliberately kept in English in brackets, for example
   `ಸಮಯ ಮಿತಿ (limitation)`, `ಬಡ್ಡಿ ಮನ್ನಾ (interest waiver)`. Keep the bracket
   when you rewrite the sentence; do not invent a Kannada-only legal term.
3. `{n}`, `{date}`, `{key}`, `{source}` are placeholders filled by the engine.
   Leave them exactly as they are.
4. Mark each row **OK**, **fix** (write the replacement) or **ask** (the English
   itself is unclear).
5. The top four warnings use details read from the engine's English sentence
   (a constant name, a source ref, a date). If those details are missing, the UI
   shows the English sentence instead, so no fact is lost.

Screens covered by this sheet: the supplier workspace (case header, claim hero,
timeline summary, readiness card, escalation ladder, eligibility pill, warning
notes, send drawer) plus the shared shell. The **Buyer CFO view stays English**
by decision: its 43 strings are not in `kn.ts`.

## A. Owner-facing MVP set (must be Kannada)

| # | Screen / card | Key | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
| 1 | Timeline summary | `timeline.title` | Timeline | ಕಾಲಾನುಕ್ರಮ (timeline) | |
| 2 | Timeline summary | `timeline.explain` | Explain dates | ದಿನಾಂಕಗಳ ಅರ್ಥ ತೋರಿಸಿ | |
| 3 | Timeline summary | `timeline.hide` | Hide explanations | ವಿವರಣೆಗಳನ್ನು ಮರೆಮಾಡಿ | |
| 4 | Evidence readiness card | `gauge.title` | Evidence readiness | ಸಾಕ್ಷ್ಯ ಸಿದ್ಧತೆ (evidence readiness) | |
| 5 | Evidence readiness card | `gauge.reasons` | What moved the score | ಅಂಕ ಬದಲಿಸಿದ ಅಂಶಗಳು | |
| 6 | Evidence readiness card | `readiness.EVIDENCE_COMPLETE` | Evidence looks complete based on what you entered | ನೀವು ನಮೂದಿಸಿದ ಮಾಹಿತಿಯ ಆಧಾರದಲ್ಲಿ ಸಾಕ್ಷ್ಯ ಪೂರ್ಣವಾಗಿ ಕಾಣುತ್ತದೆ (evidence appears complete) | |
| 7 | Evidence readiness card | `readiness.ACTION_NEEDED` | Action needed | ಕ್ರಮ ಅಗತ್ಯ (action needed) | |
| 8 | Evidence readiness card | `readiness.BLOCKED` | Blocked | ತಡೆಹಿಡಿಯಲಾಗಿದೆ (blocked) | |
| 9 | Escalation ladder | `stage.1.title` | Balance confirmation | ಬಾಕಿ ದೃಢೀಕರಣ (balance confirmation) | |
| 10 | Escalation ladder | `stage.1.purpose` | A friendly note asking the buyer to confirm the balance. | ಬಾಕಿ ಮೊತ್ತವನ್ನು ದೃಢೀಕರಿಸುವಂತೆ ಖರೀದಿದಾರರಿಗೆ ಸೌಜನ್ಯದಿಂದ ಕೇಳುವ ಟಿಪ್ಪಣಿ. | |
| 11 | Escalation ladder | `stage.2.title` | Finance-team note | ಹಣಕಾಸು ತಂಡಕ್ಕೆ ಟಿಪ್ಪಣಿ (finance-team note) | |
| 12 | Escalation ladder | `stage.2.purpose` | A calm note to their finance team on what the delay costs them. | ವಿಳಂಬವು ಅವರಿಗೆ ಏನು ವೆಚ್ಚ ತರುತ್ತದೆ ಎಂದು ಅವರ ಹಣಕಾಸು ತಂಡಕ್ಕೆ ಶಾಂತವಾಗಿ ತಿಳಿಸುವ ಟಿಪ್ಪಣಿ. | |
| 13 | Escalation ladder | `stage.3.title` | Settlement offer | ಇತ್ಯರ್ಥ ಪ್ರಸ್ತಾವ (settlement offer) | |
| 14 | Escalation ladder | `stage.3.purpose` | A split-payment offer, with an optional interest waiver. | ಭಾಗಗಳಲ್ಲಿ ಪಾವತಿಸುವ ಪ್ರಸ್ತಾವ; ಬೇಕಿದ್ದರೆ ಬಡ್ಡಿ ಮನ್ನಾ (interest waiver) ಆಯ್ಕೆಯೊಂದಿಗೆ. | |
| 15 | Escalation ladder | `stage.4.title` | Evidence pack | ಸಾಕ್ಷ್ಯ ಪ್ಯಾಕ್ (evidence pack) | |
| 16 | Escalation ladder | `stage.4.purpose` | A checklist and bundle to prepare a filing on the MSME ODR portal. | MSME ODR ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ಅರ್ಜಿ ಸಿದ್ಧಪಡಿಸಲು ಪರಿಶೀಲನಾ ಪಟ್ಟಿ (checklist) ಮತ್ತು ಸಾಕ್ಷ್ಯ ಸಂಗ್ರಹ (evidence bundle). | |
| 17 | Eligibility pill / panel | `eligibility.ELIGIBLE` | Appears eligible | ಅರ್ಹವೆಂದು ತೋರುತ್ತದೆ (eligible) | |
| 18 | Eligibility pill / panel | `eligibility.BARRED_SILPI` | Appears barred | ತಡೆಯಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (barred · Silpi) | |
| 19 | Eligibility pill / panel | `eligibility.EXCLUDED_TRADER` | Appears excluded · trader | ಹೊರಗಿಡಲಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (excluded · trader) | |
| 20 | Eligibility pill / panel | `eligibility.EXCLUDED_MEDIUM` | Appears excluded · medium | ಹೊರಗಿಡಲಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (excluded · medium) | |
| 21 | Eligibility pill / panel | `eligibility.INSUFFICIENT_DATA` | Eligibility not confirmed | ಅರ್ಹತೆ ಇನ್ನೂ ದೃಢಪಟ್ಟಿಲ್ಲ (eligibility not confirmed) | |

## B. Other translated strings

These were drafted earlier for the demo shell. They already fall back to English
where a key is missing.

| # | Screen / card | Key | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
| 1 | Top bar / footer | `app.skip` | Skip to content | ಮುಖ್ಯ ವಿಷಯಕ್ಕೆ ಹೋಗಿ | |
| 2 | Top bar / footer | `app.tagline` | Get paid on time, without losing the customer. | ಗ್ರಾಹಕರನ್ನು ಕಳೆದುಕೊಳ್ಳದೆ, ಸಮಯಕ್ಕೆ ಪಾವತಿ ಪಡೆಯಿರಿ. | |
| 3 | Shared states and badges | `badge.draft` | DRAFT | ಕರಡು (DRAFT) | |
| 4 | Shared states and badges | `badge.placeholder` | placeholder | ಮಾದರಿ (placeholder) | |
| 5 | Top bar / footer | `banner.offline` | Offline demo data. The backend is not reachable, so preset cases show results the engine saved earlier; edited cases wait for the backend. | ಆಫ್‌ಲೈನ್ ಡೆಮೊ ಡೇಟಾ (offline demo data). ಬ್ಯಾಕೆಂಡ್ ಲಭ್ಯವಿಲ್ಲ, ಆದ್ದರಿಂದ ಎಂಜಿನ್ ಮೊದಲೇ ಉಳಿಸಿದ ಫಲಿತಾಂಶಗಳನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ. | |
| 6 | Case header | `case.view.cfo` | Buyer CFO | ಖರೀದಿದಾರ CFO | |
| 7 | Case header | `case.view.supplier` | Supplier | ಪೂರೈಕೆದಾರ (supplier) | |
| 8 | Shared states and badges | `common.close` | Close | ಮುಚ್ಚಿ | |
| 9 | Shared states and badges | `common.hide` | Hide | ಮರೆಮಾಡಿ | |
| 10 | Shared states and badges | `common.why` | Why? | ಏಕೆ? | |
| 11 | Top bar / footer | `conn.checking` | Connecting | ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ | |
| 12 | Top bar / footer | `conn.live` | Engine live | ಎಂಜಿನ್ ಸಕ್ರಿಯ | |
| 13 | Top bar / footer | `conn.offline` | Offline | ಆಫ್‌ಲೈನ್ | |
| 14 | Dues list | `dues.subtitle` | Most overdue first. | ಹೆಚ್ಚು ತಡವಾದವು ಮೊದಲು. | |
| 15 | Dues list | `dues.title` | Dues | ಬಾಕಿಗಳು | |
| 16 | Eligibility pill / panel | `eligibility.see_why` | See why | ಕಾರಣ ನೋಡಿ | |
| 17 | Eligibility pill / panel | `eligibility.unconfirmed_note` | Figures are provisional until eligibility is confirmed. | ಅರ್ಹತೆ ದೃಢಪಡುವವರೆಗೆ ಅಂಕಿಅಂಶಗಳು ತಾತ್ಕಾಲಿಕ. | |
| 18 | Top bar / footer | `footer.disclaimer` | Statutory computations with cited sources. Extraction is machine-assisted and human-confirmed. Decision support, not legal advice. | ಉಲ್ಲೇಖಿತ ಮೂಲಗಳೊಂದಿಗೆ ಶಾಸನಬದ್ಧ ಲೆಕ್ಕಾಚಾರಗಳು (statutory computations). ದಾಖಲೆಗಳಿಂದ ಮಾಹಿತಿಯನ್ನು ಯಂತ್ರದ ಸಹಾಯದಿಂದ ಓದಲಾಗುತ್ತದೆ ಮತ್ತು ನೀವು ದೃಢೀಕರಿಸುತ್ತೀರಿ. ಇದು ನಿರ್ಧಾರಕ್ಕೆ ಸಹಾಯ ಮಾತ್ರ, ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ (not legal advice). | |
| 19 | Claim hero | `hero.claim` | Total claim | ಒಟ್ಟು ಕ್ಲೈಮ್ (total claim) | |
| 20 | Claim hero | `hero.interest` | Interest so far | ಇದುವರೆಗಿನ ಬಡ್ಡಿ (interest) | |
| 21 | Claim hero | `hero.next` | Next step | ಮುಂದಿನ ಹೆಜ್ಜೆ | |
| 22 | Claim hero | `hero.not_due` | Not overdue yet | ಇನ್ನೂ ತಡವಾಗಿಲ್ಲ | |
| 23 | Claim hero | `hero.overdue` | {n} days overdue | {n} ದಿನ ತಡ | |
| 24 | Claim hero | `hero.principal` | Principal | ಅಸಲು (principal) | |
| 25 | Escalation ladder | `ladder.available` | Available | ಲಭ್ಯ | |
| 26 | Escalation ladder | `ladder.blocked` | Locked | ಲಾಕ್ ಆಗಿದೆ | |
| 27 | Escalation ladder | `ladder.recommended` | Recommended | ಶಿಫಾರಸು | |
| 28 | Escalation ladder | `ladder.title` | Escalation | ಹಂತಗಳು (escalation) | |
| 29 | Top bar / footer | `nav.back_to_case` | Back to case | ಪ್ರಕರಣಕ್ಕೆ ಹಿಂತಿರುಗಿ | |
| 30 | Top bar / footer | `nav.back_to_dues` | Dues | ಬಾಕಿಗಳು | |
| 31 | Top bar / footer | `nav.dues` | Dues | ಬಾಕಿಗಳು | |
| 32 | Top bar / footer | `nav.judge` | Judge console | ತೀರ್ಪುಗಾರರ ಕನ್ಸೋಲ್ (judge console) | |
| 33 | Top bar / footer | `nav.language` | Language | ಭಾಷೆ | |
| 34 | Top bar / footer | `nav.main` | Main | ಮುಖ್ಯ | |
| 35 | Top bar / footer | `nav.upload` | Add invoice | ಇನ್‌ವಾಯ್ಸ್ ಸೇರಿಸಿ | |
| 36 | Evidence readiness card | `readiness.COURT_READY` | Evidence looks complete based on what you entered | ನೀವು ನಮೂದಿಸಿದ ಮಾಹಿತಿಯ ಆಧಾರದಲ್ಲಿ ಸಾಕ್ಷ್ಯ ಪೂರ್ಣವಾಗಿ ಕಾಣುತ್ತದೆ (evidence appears complete) | |
| 37 | Send drawer | `send.disclaimer` | Nothing is sent until you press send in your own app. | ನಿಮ್ಮ ಸ್ವಂತ ಆ್ಯಪ್‌ನಲ್ಲಿ ನೀವು ಕಳುಹಿಸುವವರೆಗೆ ಏನೂ ಕಳುಹಿಸಲಾಗುವುದಿಲ್ಲ. | |
| 38 | Shared states and badges | `state.loading` | Loading… | ಲೋಡ್ ಆಗುತ್ತಿದೆ… | |
| 39 | Shared states and badges | `state.retry` | Try again | ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ | |
| 40 | Case tabs | `tab.escalation` | Escalation | ಹಂತಗಳು (escalation) | |
| 41 | Case tabs | `tab.evidence` | Evidence & timeline | ಸಾಕ್ಷ್ಯ ಮತ್ತು ಕಾಲಾನುಕ್ರಮ | |
| 42 | Case tabs | `tab.math` | Math | ಲೆಕ್ಕಾಚಾರ (math) | |
| 43 | Case tabs | `tab.overview` | Overview | ಸಾರಾಂಶ | |

## C. The top four engine warnings

Shown in the Assumptions drawer and in send-panel notes. The code is displayed
above the sentence; the English text below is the source these drafts translate.

| # | Screen / card | Code | English source | Kannada draft | Reviewer |
|---|---|---|---|---|---|
| 1 | Assumptions drawer / send notes | `UNVERIFIED_CONSTANT` | Constant '{key}' is not verified against the statute sheet (source '{source}'). Treat any figure that depends on it as provisional. | ಸ್ಥಿರಾಂಕ '{key}' ಅನ್ನು ಇನ್ನೂ ಶಾಸನ ಪಟ್ಟಿಯೊಂದಿಗೆ (statute sheet) ಪರಿಶೀಲಿಸಿಲ್ಲ (ಮೂಲ: {source}). ಅದನ್ನು ಅವಲಂಬಿಸಿರುವ ಯಾವುದೇ ಸಂಖ್ಯೆಯನ್ನು ತಾತ್ಕಾಲಿಕ (provisional) ಎಂದು ಪರಿಗಣಿಸಿ. | |
| 2 | Assumptions drawer / send notes | `OPEN_QUESTION` | Whether the Silpi works-contract test runs from the contract date or the supply date is still an open question (OQ-2, source V4), so this check cannot decide. It is neither a pass nor a fail, and no Silpi bar is applied to this case. | ಸಿಲ್ಪಿ (Silpi) ಕೆಲಸದ ಕರಾರು ಪರೀಕ್ಷೆ ಕರಾರಿನ ದಿನಾಂಕದಿಂದ ಅಥವಾ ಪೂರೈಕೆಯ ದಿನಾಂಕದಿಂದ ಆರಂಭವಾಗುತ್ತದೆಯೇ ಎಂಬುದು ಇನ್ನೂ ತೆರೆದ ಪ್ರಶ್ನೆ (OQ-2, ಮೂಲ V4). ಆದ್ದರಿಂದ ಈ ಪರಿಶೀಲನೆ ನಿರ್ಧರಿಸಲಾಗದು; ಇದು ಉತ್ತೀರ್ಣವೂ ಅಲ್ಲ, ಅನುತ್ತೀರ್ಣವೂ ಅಲ್ಲ, ಮತ್ತು ಈ ಪ್ರಕರಣಕ್ಕೆ ಯಾವುದೇ ಸಿಲ್ಪಿ ತಡೆ ಅನ್ವಯಿಸುತ್ತಿಲ್ಲ. | |
| 3 | Assumptions drawer / send notes | `MISSING_LIMITATION_YEARS` | The config has no limitation period, so no expiry date could be worked out. The status is UNKNOWN: that is an absence of a figure, not a finding that there is time left. | ಸಮಯ ಮಿತಿಯ ಅವಧಿ (limitation period) ಕಾನ್ಫಿಗ್‌ನಲ್ಲಿ ಇಲ್ಲ, ಆದ್ದರಿಂದ ಮುಕ್ತಾಯ ದಿನಾಂಕವನ್ನು ಲೆಕ್ಕಿಸಲಾಗಿಲ್ಲ. ಸ್ಥಿತಿ UNKNOWN: ಇದು ಒಂದು ಸಂಖ್ಯೆಯ ಅನುಪಸ್ಥಿತಿ, ಸಾಕಷ್ಟು ಸಮಯ ಉಳಿದಿದೆ ಎಂಬ ತೀರ್ಮಾನ ಅಲ್ಲ. | |
| 4 | Assumptions drawer / send notes | `POTENTIAL_ACKNOWLEDGMENT` | These payment promises are recorded as potential acknowledgments but do not restart the limitation clock ({date}). A chat promise is not a signed balance confirmation or a part-payment; only those two move the date. | ಈ ಪಾವತಿ ಭರವಸೆಗಳನ್ನು ಸಂಭಾವ್ಯ ಸ್ವೀಕೃತಿಗಳಾಗಿ (potential acknowledgments) ದಾಖಲಿಸಲಾಗಿದೆ, ಆದರೆ ಅವು ಸಮಯ ಮಿತಿಯ ಗಡಿಯಾರವನ್ನು (limitation clock) ಮರುಪ್ರಾರಂಭಿಸುವುದಿಲ್ಲ ({date}). ಚಾಟ್‌ನಲ್ಲಿನ ಭರವಸೆ ಸಹಿ ಮಾಡಿದ ಬಾಕಿ ದೃಢೀಕರಣ (signed balance confirmation) ಅಥವಾ ಭಾಗ ಪಾವತಿ (part-payment) ಅಲ್ಲ; ಆ ಎರಡು ಮಾತ್ರ ದಿನಾಂಕವನ್ನು ಮುಂದೆ ಸರಿಸುತ್ತವೆ. | |

## D. Deliberately English

- **Buyer CFO view** (`cfo.*`, 43 strings): cost lines, settlement
  options and the unavailable state stay English.
- **Engine-provided text with no i18n key**: citations, assumption sentences,
  rule ids, statute references, party names, document kinds and any warning code
  outside section C are rendered as the backend sends them. That is a clean
  fallback, not a missing translation.
- **Numbers, dates and money** are never translated or re-typed; they arrive as
  placeholders or formatted by `lib/format.ts`.

## E. Sign-off

- [ ] Section A reviewed by a native speaker
- [ ] Section B reviewed by a native speaker
- [ ] Section C reviewed by a native speaker
- [ ] Legal terms still in English in brackets
- [ ] No string promises an outcome or gives legal advice
- [ ] `npm run i18n:check` passes
- [ ] `npm run smoke` language-toggle checks pass
