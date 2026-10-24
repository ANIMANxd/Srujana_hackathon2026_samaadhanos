# Statute-sheet capture checklist (V1–V11)

One row per printed primary source or screenshot. The engine's
`statute_config.json` values may only be filled from sources marked
**captured: yes**. Nothing here is invented; unknown cells stay empty.

| Ref | What it must settle (per architecture.md) | captured: yes/no | date | file |
|---|---|---|---|---|
| V1 | RBI Bank Rate history → `bank_rate_epochs[]` | no | | |
| V2 | MSMED s.2(b), s.15 (+proviso), s.16 → objection window, credit cap, interest multiplier | no | | |
| V3 | s.43B(h) IT timing, buyer tax presets → `section_43bh_first_fy`, `tax_presets[]` | no | | |
| V4 | Silpi works-contract test date → `silpi_test_date` | no | | |
| V5 | NIC codes treated as trading → `trader_nic_prefixes` | no | | |
| V6 | MSME investment/turnover limits by date → `size_epochs[]` | no | | |
| V7 | Limitation period for price of goods/services + acknowledgment rules → `limitation_years` | no | | |
| V8 | (not named in architecture.md — capture whatever the spec's source list assigns to V8) | no | | |
| V9 | Buyer pressure points: GST credit reversal, MSME-1 return, appeal deposit → `gated_features` | no | | |
| V10 | (not named in architecture.md — capture whatever the spec's source list assigns to V10) | no | | |
| V11 | Event rules (pasted verbatim into `docs/event-rules.md`) | no | | |

Fill the `date` and `file` columns when a capture lands in this folder.
Aniruddha verifies V1 (Bank Rate epochs) first — the demo's headline number
depends on it (architecture.md section 12, trap 1).
