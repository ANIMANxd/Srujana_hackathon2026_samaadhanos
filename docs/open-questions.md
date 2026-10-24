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

## New entries

Append below with: the rule, where it appears, what you believe is wrong or
missing, and what source would settle it.
