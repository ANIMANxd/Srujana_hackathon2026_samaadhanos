// Kannada (spec v3.3 C8 stretch; architecture §10: "kn.ts covers the MVP card
// set, with legal terms kept in English in brackets"). Any missing key falls
// back to English, so screens never show a blank.
//
// REVIEW NEEDED: every string below carries a // NEEDS-NATIVE-REVIEW marker.
// A native Kannada speaker must check each one before it is shown to real
// users. docs/kannada-review.md lists every string with its English source and
// is generated from this file (`npm run i18n:doc`).
//
// Wording rules from en.ts apply: cautious, no "guaranteed", no legal
// conclusions. Numbers and dates are never typed here; they arrive as
// {placeholders}. English is the source of truth: this file never adds a fact
// that the English string does not already carry.
//
// The Buyer CFO view (cfo.*) stays English on purpose (task: owner-facing MVP
// set only). Its strings are deliberately absent here; do not add them without
// an explicit decision to translate that persona.

import type { MessageKey } from "./en";

export const kn: Partial<Record<MessageKey, string>> = {
  // shell
  // NEEDS-NATIVE-REVIEW
  "app.tagline": "ಗ್ರಾಹಕರನ್ನು ಕಳೆದುಕೊಳ್ಳದೆ, ಸಮಯಕ್ಕೆ ಪಾವತಿ ಪಡೆಯಿರಿ.",
  // NEEDS-NATIVE-REVIEW
  "app.skip": "ಮುಖ್ಯ ವಿಷಯಕ್ಕೆ ಹೋಗಿ",
  // NEEDS-NATIVE-REVIEW
  "nav.dues": "ಬಾಕಿಗಳು",
  // NEEDS-NATIVE-REVIEW
  "nav.upload": "ಇನ್‌ವಾಯ್ಸ್ ಸೇರಿಸಿ",
  // NEEDS-NATIVE-REVIEW
  "nav.back_to_dues": "ಬಾಕಿಗಳು",
  // NEEDS-NATIVE-REVIEW
  "nav.back_to_case": "ಪ್ರಕರಣಕ್ಕೆ ಹಿಂತಿರುಗಿ",
  // NEEDS-NATIVE-REVIEW
  "nav.main": "ಮುಖ್ಯ",
  // NEEDS-NATIVE-REVIEW
  "nav.judge": "ತೀರ್ಪುಗಾರರ ಕನ್ಸೋಲ್ (judge console)",
  // NEEDS-NATIVE-REVIEW
  "nav.language": "ಭಾಷೆ",
  // NEEDS-NATIVE-REVIEW
  "conn.live": "ಎಂಜಿನ್ ಸಕ್ರಿಯ",
  // NEEDS-NATIVE-REVIEW
  "conn.offline": "ಆಫ್‌ಲೈನ್",
  // NEEDS-NATIVE-REVIEW
  "banner.offline":
    "ಆಫ್‌ಲೈನ್ ಡೆಮೊ ಡೇಟಾ (offline demo data). ಬ್ಯಾಕೆಂಡ್ ಲಭ್ಯವಿಲ್ಲ, ಆದ್ದರಿಂದ ಎಂಜಿನ್ ಮೊದಲೇ ಉಳಿಸಿದ ಫಲಿತಾಂಶಗಳನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ.",
  // NEEDS-NATIVE-REVIEW
  "conn.checking": "ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ",
  // NEEDS-NATIVE-REVIEW
  "footer.disclaimer":
    "ಉಲ್ಲೇಖಿತ ಮೂಲಗಳೊಂದಿಗೆ ಶಾಸನಬದ್ಧ ಲೆಕ್ಕಾಚಾರಗಳು (statutory computations). ದಾಖಲೆಗಳಿಂದ ಮಾಹಿತಿಯನ್ನು ಯಂತ್ರದ ಸಹಾಯದಿಂದ ಓದಲಾಗುತ್ತದೆ ಮತ್ತು ನೀವು ದೃಢೀಕರಿಸುತ್ತೀರಿ. ಇದು ನಿರ್ಧಾರಕ್ಕೆ ಸಹಾಯ ಮಾತ್ರ, ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ (not legal advice).",

  // states
  // NEEDS-NATIVE-REVIEW
  "state.loading": "ಲೋಡ್ ಆಗುತ್ತಿದೆ…",
  // NEEDS-NATIVE-REVIEW
  "state.retry": "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
  // NEEDS-NATIVE-REVIEW
  "common.close": "ಮುಚ್ಚಿ",
  // NEEDS-NATIVE-REVIEW
  "common.why": "ಏಕೆ?",
  // NEEDS-NATIVE-REVIEW
  "common.hide": "ಮರೆಮಾಡಿ",
  // NEEDS-NATIVE-REVIEW
  "badge.draft": "ಕರಡು (DRAFT)",
  // NEEDS-NATIVE-REVIEW
  "badge.placeholder": "ಮಾದರಿ (placeholder)",

  // dues
  // NEEDS-NATIVE-REVIEW
  "dues.title": "ಬಾಕಿಗಳು",
  // NEEDS-NATIVE-REVIEW
  "dues.subtitle": "ಹೆಚ್ಚು ತಡವಾದವು ಮೊದಲು.",

  // tabs
  // NEEDS-NATIVE-REVIEW
  "tab.overview": "ಸಾರಾಂಶ",
  // NEEDS-NATIVE-REVIEW
  "tab.evidence": "ಸಾಕ್ಷ್ಯ ಮತ್ತು ಕಾಲಾನುಕ್ರಮ",
  // NEEDS-NATIVE-REVIEW
  "tab.math": "ಲೆಕ್ಕಾಚಾರ (math)",
  // NEEDS-NATIVE-REVIEW
  "tab.escalation": "ಹಂತಗಳು (escalation)",

  // case card (MVP set)
  // NEEDS-NATIVE-REVIEW
  "case.view.supplier": "ಪೂರೈಕೆದಾರ (supplier)",
  // NEEDS-NATIVE-REVIEW
  "case.view.cfo": "ಖರೀದಿದಾರ CFO",
  // NEEDS-NATIVE-REVIEW
  "hero.claim": "ಒಟ್ಟು ಕ್ಲೈಮ್ (total claim)",
  // NEEDS-NATIVE-REVIEW
  "hero.principal": "ಅಸಲು (principal)",
  // NEEDS-NATIVE-REVIEW
  "hero.interest": "ಇದುವರೆಗಿನ ಬಡ್ಡಿ (interest)",
  // NEEDS-NATIVE-REVIEW
  "hero.overdue": "{n} ದಿನ ತಡ",
  // NEEDS-NATIVE-REVIEW
  "hero.not_due": "ಇನ್ನೂ ತಡವಾಗಿಲ್ಲ",
  // NEEDS-NATIVE-REVIEW
  "hero.next": "ಮುಂದಿನ ಹೆಜ್ಜೆ",

  // eligibility pill (MVP set)
  // NEEDS-NATIVE-REVIEW
  "eligibility.ELIGIBLE": "ಅರ್ಹವೆಂದು ತೋರುತ್ತದೆ (eligible)",
  // NEEDS-NATIVE-REVIEW
  "eligibility.BARRED_SILPI": "ತಡೆಯಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (barred · Silpi)",
  // NEEDS-NATIVE-REVIEW
  "eligibility.EXCLUDED_TRADER": "ಹೊರಗಿಡಲಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (excluded · trader)",
  // NEEDS-NATIVE-REVIEW
  "eligibility.EXCLUDED_MEDIUM": "ಹೊರಗಿಡಲಾಗಿದೆ ಎಂದು ತೋರುತ್ತದೆ (excluded · medium)",
  // NEEDS-NATIVE-REVIEW
  "eligibility.INSUFFICIENT_DATA": "ಅರ್ಹತೆ ಇನ್ನೂ ದೃಢಪಟ್ಟಿಲ್ಲ (eligibility not confirmed)",
  // NEEDS-NATIVE-REVIEW
  "eligibility.unconfirmed_note": "ಅರ್ಹತೆ ದೃಢಪಡುವವರೆಗೆ ಅಂಕಿಅಂಶಗಳು ತಾತ್ಕಾಲಿಕ.",
  // NEEDS-NATIVE-REVIEW
  "eligibility.see_why": "ಕಾರಣ ನೋಡಿ",

  // escalation ladder stage titles and one-line purposes (MVP set)
  // NEEDS-NATIVE-REVIEW
  "stage.1.title": "ಬಾಕಿ ದೃಢೀಕರಣ (balance confirmation)",
  // NEEDS-NATIVE-REVIEW
  "stage.1.purpose": "ಬಾಕಿ ಮೊತ್ತವನ್ನು ದೃಢೀಕರಿಸುವಂತೆ ಖರೀದಿದಾರರಿಗೆ ಸೌಜನ್ಯದಿಂದ ಕೇಳುವ ಟಿಪ್ಪಣಿ.",
  // NEEDS-NATIVE-REVIEW
  "stage.2.title": "ಹಣಕಾಸು ತಂಡಕ್ಕೆ ಟಿಪ್ಪಣಿ (finance-team note)",
  // NEEDS-NATIVE-REVIEW
  "stage.2.purpose": "ವಿಳಂಬವು ಅವರಿಗೆ ಏನು ವೆಚ್ಚ ತರುತ್ತದೆ ಎಂದು ಅವರ ಹಣಕಾಸು ತಂಡಕ್ಕೆ ಶಾಂತವಾಗಿ ತಿಳಿಸುವ ಟಿಪ್ಪಣಿ.",
  // NEEDS-NATIVE-REVIEW
  "stage.3.title": "ಇತ್ಯರ್ಥ ಪ್ರಸ್ತಾವ (settlement offer)",
  // NEEDS-NATIVE-REVIEW
  "stage.3.purpose": "ಭಾಗಗಳಲ್ಲಿ ಪಾವತಿಸುವ ಪ್ರಸ್ತಾವ; ಬೇಕಿದ್ದರೆ ಬಡ್ಡಿ ಮನ್ನಾ (interest waiver) ಆಯ್ಕೆಯೊಂದಿಗೆ.",
  // NEEDS-NATIVE-REVIEW
  "stage.4.title": "ಸಾಕ್ಷ್ಯ ಪ್ಯಾಕ್ (evidence pack)",
  // NEEDS-NATIVE-REVIEW
  "stage.4.purpose": "MSME ODR ಪೋರ್ಟಲ್‌ನಲ್ಲಿ ಅರ್ಜಿ ಸಿದ್ಧಪಡಿಸಲು ಪರಿಶೀಲನಾ ಪಟ್ಟಿ (checklist) ಮತ್ತು ಸಾಕ್ಷ್ಯ ಸಂಗ್ರಹ (evidence bundle).",
  // NEEDS-NATIVE-REVIEW
  "ladder.title": "ಹಂತಗಳು (escalation)",
  // NEEDS-NATIVE-REVIEW
  "ladder.recommended": "ಶಿಫಾರಸು",
  // NEEDS-NATIVE-REVIEW
  "ladder.available": "ಲಭ್ಯ",
  // NEEDS-NATIVE-REVIEW
  "ladder.blocked": "ಲಾಕ್ ಆಗಿದೆ",

  // evidence readiness: card heading, band and reasons heading (MVP set)
  // NEEDS-NATIVE-REVIEW
  "gauge.title": "ಸಾಕ್ಷ್ಯ ಸಿದ್ಧತೆ (evidence readiness)",
  // NEEDS-NATIVE-REVIEW
  "gauge.reasons": "ಅಂಕ ಬದಲಿಸಿದ ಅಂಶಗಳು",
  // NEEDS-NATIVE-REVIEW
  "readiness.COURT_READY": "ನೀವು ನಮೂದಿಸಿದ ಮಾಹಿತಿಯ ಆಧಾರದಲ್ಲಿ ಸಾಕ್ಷ್ಯ ಪೂರ್ಣವಾಗಿ ಕಾಣುತ್ತದೆ (evidence appears complete)",
  // NEEDS-NATIVE-REVIEW
  "readiness.EVIDENCE_COMPLETE": "ನೀವು ನಮೂದಿಸಿದ ಮಾಹಿತಿಯ ಆಧಾರದಲ್ಲಿ ಸಾಕ್ಷ್ಯ ಪೂರ್ಣವಾಗಿ ಕಾಣುತ್ತದೆ (evidence appears complete)",
  // NEEDS-NATIVE-REVIEW
  "readiness.ACTION_NEEDED": "ಕ್ರಮ ಅಗತ್ಯ (action needed)",
  // NEEDS-NATIVE-REVIEW
  "readiness.BLOCKED": "ತಡೆಹಿಡಿಯಲಾಗಿದೆ (blocked)",

  // timeline summary card (MVP set)
  // NEEDS-NATIVE-REVIEW
  "timeline.title": "ಕಾಲಾನುಕ್ರಮ (timeline)",
  // NEEDS-NATIVE-REVIEW
  "timeline.explain": "ದಿನಾಂಕಗಳ ಅರ್ಥ ತೋರಿಸಿ",
  // NEEDS-NATIVE-REVIEW
  "timeline.hide": "ವಿವರಣೆಗಳನ್ನು ಮರೆಮಾಡಿ",

  // send
  // NEEDS-NATIVE-REVIEW
  "send.disclaimer": "ನಿಮ್ಮ ಸ್ವಂತ ಆ್ಯಪ್‌ನಲ್ಲಿ ನೀವು ಕಳುಹಿಸುವವರೆಗೆ ಏನೂ ಕಳುಹಿಸಲಾಗುವುದಿಲ್ಲ.",
};

/**
 * The four engine warning codes an owner meets on the main demo case
 * (case_01): UNVERIFIED_CONSTANT, OPEN_QUESTION, MISSING_LIMITATION_YEARS and
 * POTENTIAL_ACKNOWLEDGMENT. Other codes fall back to the backend's English
 * sentence, which always carries the case-specific detail.
 *
 * `en` is kept here only so docs/kannada-review.md can quote the source next to
 * the draft; the English UI never renders it (it renders the engine's text).
 * `needsVars` names the placeholders read from that English sentence before the
 * Kannada string is used. If a detail cannot be read, the UI shows English
 * rather than a sentence with a missing fact.
 */
export type KnWarning = {
  code: string;
  en: string;
  kn: string;
  needsVars: readonly string[];
};

export const knWarnings: readonly KnWarning[] = [
  // NEEDS-NATIVE-REVIEW
  {
    code: "UNVERIFIED_CONSTANT",
    en: "Constant '{key}' is not verified against the statute sheet (source '{source}'). Treat any figure that depends on it as provisional.",
    kn: "ಸ್ಥಿರಾಂಕ '{key}' ಅನ್ನು ಇನ್ನೂ ಶಾಸನ ಪಟ್ಟಿಯೊಂದಿಗೆ (statute sheet) ಪರಿಶೀಲಿಸಿಲ್ಲ (ಮೂಲ: {source}). ಅದನ್ನು ಅವಲಂಬಿಸಿರುವ ಯಾವುದೇ ಸಂಖ್ಯೆಯನ್ನು ತಾತ್ಕಾಲಿಕ (provisional) ಎಂದು ಪರಿಗಣಿಸಿ.",
    needsVars: ["key", "source"],
  },
  // NEEDS-NATIVE-REVIEW
  {
    code: "OPEN_QUESTION",
    en: "Whether the Silpi works-contract test runs from the contract date or the supply date is still an open question (OQ-2, source V4), so this check cannot decide. It is neither a pass nor a fail, and no Silpi bar is applied to this case.",
    kn: "ಸಿಲ್ಪಿ (Silpi) ಕೆಲಸದ ಕರಾರು ಪರೀಕ್ಷೆ ಕರಾರಿನ ದಿನಾಂಕದಿಂದ ಅಥವಾ ಪೂರೈಕೆಯ ದಿನಾಂಕದಿಂದ ಆರಂಭವಾಗುತ್ತದೆಯೇ ಎಂಬುದು ಇನ್ನೂ ತೆರೆದ ಪ್ರಶ್ನೆ (OQ-2, ಮೂಲ V4). ಆದ್ದರಿಂದ ಈ ಪರಿಶೀಲನೆ ನಿರ್ಧರಿಸಲಾಗದು; ಇದು ಉತ್ತೀರ್ಣವೂ ಅಲ್ಲ, ಅನುತ್ತೀರ್ಣವೂ ಅಲ್ಲ, ಮತ್ತು ಈ ಪ್ರಕರಣಕ್ಕೆ ಯಾವುದೇ ಸಿಲ್ಪಿ ತಡೆ ಅನ್ವಯಿಸುತ್ತಿಲ್ಲ.",
    needsVars: [],
  },
  // NEEDS-NATIVE-REVIEW
  {
    code: "MISSING_LIMITATION_YEARS",
    en: "The config has no limitation period, so no expiry date could be worked out. The status is UNKNOWN: that is an absence of a figure, not a finding that there is time left.",
    kn: "ಸಮಯ ಮಿತಿಯ ಅವಧಿ (limitation period) ಕಾನ್ಫಿಗ್‌ನಲ್ಲಿ ಇಲ್ಲ, ಆದ್ದರಿಂದ ಮುಕ್ತಾಯ ದಿನಾಂಕವನ್ನು ಲೆಕ್ಕಿಸಲಾಗಿಲ್ಲ. ಸ್ಥಿತಿ UNKNOWN: ಇದು ಒಂದು ಸಂಖ್ಯೆಯ ಅನುಪಸ್ಥಿತಿ, ಸಾಕಷ್ಟು ಸಮಯ ಉಳಿದಿದೆ ಎಂಬ ತೀರ್ಮಾನ ಅಲ್ಲ.",
    needsVars: [],
  },
  // NEEDS-NATIVE-REVIEW
  {
    code: "POTENTIAL_ACKNOWLEDGMENT",
    en: "These payment promises are recorded as potential acknowledgments but do not restart the limitation clock ({date}). A chat promise is not a signed balance confirmation or a part-payment; only those two move the date.",
    kn: "ಈ ಪಾವತಿ ಭರವಸೆಗಳನ್ನು ಸಂಭಾವ್ಯ ಸ್ವೀಕೃತಿಗಳಾಗಿ (potential acknowledgments) ದಾಖಲಿಸಲಾಗಿದೆ, ಆದರೆ ಅವು ಸಮಯ ಮಿತಿಯ ಗಡಿಯಾರವನ್ನು (limitation clock) ಮರುಪ್ರಾರಂಭಿಸುವುದಿಲ್ಲ ({date}). ಚಾಟ್‌ನಲ್ಲಿನ ಭರವಸೆ ಸಹಿ ಮಾಡಿದ ಬಾಕಿ ದೃಢೀಕರಣ (signed balance confirmation) ಅಥವಾ ಭಾಗ ಪಾವತಿ (part-payment) ಅಲ್ಲ; ಆ ಎರಡು ಮಾತ್ರ ದಿನಾಂಕವನ್ನು ಮುಂದೆ ಸರಿಸುತ್ತವೆ.",
    needsVars: ["date"],
  },
];

export const knWarningMap: Readonly<Record<string, KnWarning>> = Object.fromEntries(
  knWarnings.map((w) => [w.code, w]),
);

/**
 * Owner-facing MVP keys this dictionary must cover. The language-toggle check
 * (scripts/i18n-check.mjs) fails if any is missing, blank or not Kannada, and
 * docs/kannada-review.md lists them first for the reviewer.
 */
export const knMvpKeys = [
  "timeline.title",
  "timeline.explain",
  "timeline.hide",
  "gauge.title",
  "gauge.reasons",
  "readiness.EVIDENCE_COMPLETE",
  "readiness.ACTION_NEEDED",
  "readiness.BLOCKED",
  "stage.1.title",
  "stage.1.purpose",
  "stage.2.title",
  "stage.2.purpose",
  "stage.3.title",
  "stage.3.purpose",
  "stage.4.title",
  "stage.4.purpose",
  "eligibility.ELIGIBLE",
  "eligibility.BARRED_SILPI",
  "eligibility.EXCLUDED_TRADER",
  "eligibility.EXCLUDED_MEDIUM",
  "eligibility.INSUFFICIENT_DATA",
] as const satisfies readonly MessageKey[];
