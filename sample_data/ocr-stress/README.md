# OCR stress set

These files are for the OCR layer, not for the case flow. Each one is derived
from a clean document by a degradation that a real supplier's paperwork suffers.

| File | What it tests |
|---|---|
| `01-degraded/...-rotated.pdf` | 1.8-degree skew; deskew before line segmentation |
| `01-degraded/...-low-contrast.pdf` | washed-out photocopy; binarisation and thresholding |
| `01-degraded/...-photocopy.pdf` | generational copy with speckle and streak lines |
| `01-degraded/...-cropped-total.pdf` | the amounts column is cut off. **Amount must come back missing.** |
| `01-degraded/...-stamp-over-total.pdf` | a rubber stamp over the totals |
| `02-photos/...-phone-photo.jpg` | tilt, edge shadow, JPEG q48 |
| `02-photos/...-phone-photo-low-light.jpg` | brightness 0.72, contrast 0.75, JPEG q40 |
| `03-multipage/INV-2026-MP01.pdf` | 30 line items; the total is on the last page |
| `04-edge-cases/INV-2026-EDGE01-ambiguous-dates.pdf` | 10/03/2026 and 04/05/2026: both readings are valid |
| `04-edge-cases/INV-2026-EDGE02-no-total.pdf` | no Grand Total line at all |
| `04-edge-cases/INV-2026-EDGE03-no-gstin.pdf` | no GSTIN on the page |
| `05-chats/chat_ios_format.txt` | iOS `[date, time] Sender:` header |
| `05-chats/chat_hinglish.txt` | English-only tagger meets Hinglish; expect `NO_CANDIDATES` |
| `05-chats/chat_group_continuation.txt` | system line plus a wrapped message |

`MANIFEST.json` holds the ground truth. For every file it gives `expected`, the
values a correct reader should produce, and `notes` saying what the specific
degradation is meant to defeat. Compare your OCR output against it; do not
tune the manifest to make a reading pass.
