// Kannada (spec v3.3 C8 stretch; architecture §10: "kn.ts covers the MVP card
// set, with legal terms kept in English in brackets"). Any missing key falls
// back to English, so screens never show a blank.
//
// REVIEW NEEDED: drafted for the demo shell and the main case card; a native
// speaker must check every string before it is shown to real users. Wording
// rules from en.ts apply: cautious, no "guaranteed", no legal conclusions.
// Numbers and dates are never typed here; they arrive as {placeholders}.

import type { MessageKey } from "./en";

export const kn: Partial<Record<MessageKey, string>> = {
  // shell
  "app.tagline": "ಗ್ರಾಹಕರನ್ನು ಕಳೆದುಕೊಳ್ಳದೆ, ಸಮಯಕ್ಕೆ ಪಾವತಿ ಪಡೆಯಿರಿ.",
  "app.skip": "ಮುಖ್ಯ ವಿಷಯಕ್ಕೆ ಹೋಗಿ",
  "nav.dues": "ಬಾಕಿಗಳು",
  "nav.upload": "ಇನ್‌ವಾಯ್ಸ್ ಸೇರಿಸಿ",
  "nav.back_to_dues": "ಬಾಕಿಗಳು",
  "nav.back_to_case": "ಪ್ರಕರಣಕ್ಕೆ ಹಿಂತಿರುಗಿ",
  "nav.main": "ಮುಖ್ಯ",
  "nav.judge": "ತೀರ್ಪುಗಾರರ ಕನ್ಸೋಲ್ (judge console)",
  "nav.language": "ಭಾಷೆ",
  "conn.live": "ಎಂಜಿನ್ ಸಕ್ರಿಯ",
  "conn.offline": "ಆಫ್‌ಲೈನ್",
  "banner.offline":
    "ಆಫ್‌ಲೈನ್ ಡೆಮೊ ಡೇಟಾ (offline demo data). ಬ್ಯಾಕೆಂಡ್ ಲಭ್ಯವಿಲ್ಲ, ಆದ್ದರಿಂದ ಎಂಜಿನ್ ಮೊದಲೇ ಉಳಿಸಿದ ಫಲಿತಾಂಶಗಳನ್ನು ತೋರಿಸಲಾಗುತ್ತಿದೆ.",
  "conn.checking": "ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ",
  "footer.disclaimer":
    "ಉಲ್ಲೇಖಿತ ಮೂಲಗಳೊಂದಿಗೆ ಶಾಸನಬದ್ಧ ಲೆಕ್ಕಾಚಾರಗಳು (statutory computations). ದಾಖಲೆಗಳಿಂದ ಮಾಹಿತಿಯನ್ನು ಯಂತ್ರದ ಸಹಾಯದಿಂದ ಓದಲಾಗುತ್ತದೆ ಮತ್ತು ನೀವು ದೃಢೀಕರಿಸುತ್ತೀರಿ. ಇದು ನಿರ್ಧಾರಕ್ಕೆ ಸಹಾಯ ಮಾತ್ರ, ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ (not legal advice).",

  // states
  "state.loading": "ಲೋಡ್ ಆಗುತ್ತಿದೆ…",
  "state.retry": "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
  "common.close": "ಮುಚ್ಚಿ",
  "common.why": "ಏಕೆ?",
  "common.hide": "ಮರೆಮಾಡಿ",
  "badge.draft": "ಕರಡು (DRAFT)",
  "badge.placeholder": "ಮಾದರಿ (placeholder)",

  // dues
  "dues.title": "ಬಾಕಿಗಳು",
  "dues.subtitle": "ಹೆಚ್ಚು ತಡವಾದವು ಮೊದಲು.",

  // tabs
  "tab.overview": "ಸಾರಾಂಶ",
  "tab.evidence": "ಸಾಕ್ಷ್ಯ ಮತ್ತು ಕಾಲಾನುಕ್ರಮ",
  "tab.math": "ಲೆಕ್ಕಾಚಾರ (math)",
  "tab.escalation": "ಹಂತಗಳು (escalation)",

  // case card (MVP set)
  "case.view.supplier": "ಪೂರೈಕೆದಾರ (supplier)",
  "case.view.cfo": "ಖರೀದಿದಾರ CFO",
  "hero.claim": "ಒಟ್ಟು ಕ್ಲೈಮ್ (total claim)",
  "hero.principal": "ಅಸಲು (principal)",
  "hero.interest": "ಇದುವರೆಗಿನ ಬಡ್ಡಿ (interest)",
  "hero.overdue": "{n} ದಿನ ತಡ",
  "hero.not_due": "ಇನ್ನೂ ತಡವಾಗಿಲ್ಲ",
  "hero.next": "ಮುಂದಿನ ಹೆಜ್ಜೆ",
  "eligibility.ELIGIBLE": "ಅರ್ಹವೆಂದು ತೋರುತ್ತದೆ",
  "eligibility.INSUFFICIENT_DATA": "ಅರ್ಹತೆ ಇನ್ನೂ ದೃಢಪಟ್ಟಿಲ್ಲ (eligibility not confirmed)",
  "eligibility.unconfirmed_note": "ಅರ್ಹತೆ ದೃಢಪಡುವವರೆಗೆ ಅಂಕಿಅಂಶಗಳು ತಾತ್ಕಾಲಿಕ.",
  "eligibility.see_why": "ಕಾರಣ ನೋಡಿ",
  "stage.1.title": "ಬಾಕಿ ದೃಢೀಕರಣ (balance confirmation)",
  "stage.2.title": "ಹಣಕಾಸು ತಂಡಕ್ಕೆ ಟಿಪ್ಪಣಿ",
  "stage.3.title": "ಇತ್ಯರ್ಥ ಪ್ರಸ್ತಾವ (settlement offer)",
  "stage.4.title": "ಸಾಕ್ಷ್ಯ ಪ್ಯಾಕ್ (evidence pack)",
  "ladder.title": "ಹಂತಗಳು (escalation)",
  "ladder.recommended": "ಶಿಫಾರಸು",
  "ladder.available": "ಲಭ್ಯ",
  "ladder.blocked": "ಲಾಕ್ ಆಗಿದೆ",
  "send.disclaimer": "ನಿಮ್ಮ ಸ್ವಂತ ಆ್ಯಪ್‌ನಲ್ಲಿ ನೀವು ಕಳುಹಿಸುವವರೆಗೆ ಏನೂ ಕಳುಹಿಸಲಾಗುವುದಿಲ್ಲ.",
};
