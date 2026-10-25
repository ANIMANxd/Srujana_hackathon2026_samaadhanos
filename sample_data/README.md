# Sample documents (synthetic)

Actual PDF files, readable text twins and WhatsApp exports for OCR development
and for the judge demo. Everything here is **fictional**. Nothing in this folder
is a real tax invoice, purchase order, government certificate, notice or filing.

Read [`MANIFEST.json`](MANIFEST.json) for the ground truth: for every file, the
values a correct reader should produce, the warning the extractor should raise,
and what the specific degradation is meant to defeat.

## Safety rules this corpus follows

These are the AGENTS.md rules, applied to paper:

- **Synthetic only.** Every party ends in `(synthetic)` or `(fictional)`. There
  are no real names, phone numbers, addresses or UTRs. Email addresses use the
  reserved `.invalid` domain.
- **The GSTINs are deliberately invalid.** They use the `29SYN...` placeholder
  shape (16 characters, a `SYN` "PAN"), so they cannot belong to a real
  registered person. `verify_samples.py` scans every text file and fails if any
  15-character, structurally valid GSTIN appears.
- **No official documents.** There is no Udyam certificate, no e-way bill, no
  MSEFC form and no notice, because faking one would break golden rule 9. The
  Udyam page is a **data extract**, headed *NOT AN UDYAM REGISTRATION
  CERTIFICATE*, and the GST returns are labelled synthetic extracts, not portal
  documents.
- **No impersonation.** No real bank, TReDS platform or government name, logo or
  page styling. The bank is "Fictional Bank A"; the chat renders have no
  platform logo.
- **Every page says so.** A red SPECIMEN banner, a diagonal watermark and a
  footer appear on every PDF. The `.txt` twins start with the same statement.

**Do not add a real supplier's documents here.** This folder is committed to git.

## What is inside

```
sample_data/
  MANIFEST.json                 ground truth for every file
  generate_samples.py           rebuilds the whole corpus, deterministically
  verify_samples.py             runs the real extractor against the ground truth
  case-01-sample-supplies/      golden path: overdue, Net-90, promise to pay
  case-02-micro-works/          written objection on day 9, resolved on day 18
  case-04-fabricators/          ambiguous date, part payment
  case-06-maintenance/          service invoice, no delivery date or proof
  supplier-records/             Udyam extracts and GST return extracts
  ocr-stress/                   degraded scans, photos, multipage, edge cases
```

Each document exists as a PDF **and** a `.txt` twin written from the same
content model, so the two can never drift. The PDF is the OCR target; the twin
is what the current `/extract-evidence` endpoint can read today.

### The four cases

| Case | Story | Preset it mirrors |
|---|---|---|
| `case-01-sample-supplies` | 12,50,000.00 invoice, no objection, a WhatsApp promise on 10/04/2026 | `case_01` |
| `case-02-micro-works` | 3,00,000.00 invoice, buyer objects in writing on day 9, replacement on day 18 | `case_02` |
| `case-04-fabricators` | 5,00,000.00 invoice, 1,50,000.00 part payment on 15/05/2026 | `case_04` |
| `case-06-maintenance` | 2,50,000.00 service invoice with **no delivery date and no delivery proof** | `case_06` |

The amounts, dates and objection dates match the preset fixtures in
`contracts/fixtures/`. The supplier GSTINs are distinct placeholders because the
presets reuse neighbouring numbers for different buyers.

### Which evidence kind each file feeds

| `EvidenceKind` | File |
|---|---|
| `PO` | `case-*/01-purchase-order/*.pdf` |
| `INVOICE` | `case-*/0*-tax-invoice/*.pdf` |
| `DELIVERY_PROOF` | `case-01/03-delivery/DC-2026-0088.pdf` and `GRN-2026-0088.pdf`, `case-02/03-delivery/DC-2026-0209.pdf` |
| `WHATSAPP` | `case-*/0*-whatsapp/*.txt` |
| `UDYAM` | `supplier-records/01-udyam/*.pdf` |
| `GST_RETURN` | `supplier-records/02-gst-return/*.pdf` |

A written objection and a remittance advice are not evidence kinds in the
contract; they feed the `objections[]` and `part_payments[]` arrays instead.

## Rebuilding and checking

```bash
python sample_data/generate_samples.py     # rebuild every file and the manifest
python sample_data/verify_samples.py       # ground truth vs the real extractor
python sample_data/verify_samples.py -v    # one line per file
```

The generator needs `reportlab` (already in `requirements.txt`) and, for the
scan and photo variants, `pymupdf` and `pillow`:

```bash
pip install pymupdf pillow
```

`verify_samples.py` fails when:

- a file is on disk but missing from `MANIFEST.json`, or the reverse;
- a `.txt` twin or chat export produces a different field value than the
  manifest promises;
- a chat produces different tags or a different `days_after_delivery`;
- a "digital" PDF has no text layer, or a scan/photo **does** have one;
- a page count differs from the manifest;
- any text file contains a structurally valid 15-character GSTIN (the corpus is
  placeholder-only).

It imports `backend.extraction`, so run it from the repository root with the
backend dependencies installed. It never edits the ground truth.

The digital PDFs are byte-stable (`rl_config.invariant`). The degraded scans are
re-rasterised on each run, so their bytes can change with a Pillow or PyMuPDF
upgrade; that is expected.

## What the OCR layer should do

The intended flow is:

```
PDF or photo -> your OCR -> plain text -> POST /api/v1/extract-evidence
             -> every value shown with its line citation -> human confirms
             -> engine
```

`POST /extract-evidence` reads **plain text only** today: a binary upload is
refused with advice (`backend/extraction/text.py`). That is why every PDF has a
`.txt` twin. Until OCR lands, you can demo the whole chain by uploading a twin.

The extractor is **line-anchored**: it recognises `Tax Invoice No: INV-2026-0042`
on one line, not a label on one line and its value on the next. A PDF's own text
layer splits the key/value columns apart, and some OCR engines do the same. When
you build the OCR layer, join each label to its value on one visual row; the
`.txt` twins show the shape the extractor expects.

Ground truth for a file is under `expected` in the manifest. Two habits matter:

1. **Report a missing value as missing.** `ocr-stress/01-degraded/INV-2026-0042-cropped-total.pdf`
   has no readable Grand Total, and `ocr-stress/04-edge-cases/INV-2026-EDGE02-no-total.pdf`
   has no Grand Total line at all. Both expect `"amount": null`. Guessing a
   number is worse than returning nothing, because a human may confirm it.
2. **Surface ambiguity, do not resolve it.** `case-04`, `case-06` and
   `ocr-stress/04-edge-cases/INV-2026-EDGE01-ambiguous-dates.pdf` contain dates
   like `10/03/2026`, which is valid DD/MM and valid MM/DD. The manifest expects
   the Indian reading **and** a `DATE_ORDER_ASSUMED` warning. Never silently
   pick one.

If your OCR emits a field key the manifest does not list, ignore it. If it emits
a different value, the disagreement is the interesting part: check whether the
degradation explains it before changing an expectation.

## Manifest schema

Each entry in `files[]`:

| Key | Meaning |
|---|---|
| `file` | path relative to this folder |
| `role` | `document`, `text_twin`, `chat_export`, `chat_render`, `derived`, `source` |
| `doc_type` | e.g. `TAX_INVOICE`, `PURCHASE_ORDER`, `GST_RETURN_EXTRACT` |
| `evidence_kind` | the contract's `EvidenceKind`, or `null` |
| `case` | which case folder it belongs to, or `""` |
| `render` | `digital`, `text`, `scanned`, `photo`, `raster`, `email` |
| `text_layer` | `true`, `false`, or `null` when the question does not apply |
| `pages` | page count where known |
| `expected` | the values a correct reader produces (`null` means "must be missing") |
| `text_layer_must_contain` | strings a digital PDF's text layer must carry |
| `expected_warnings` | warning codes the extractor must raise |
| `not_expected_warnings` | codes that must be absent |
| `expected_messages` | for chats: message snippet, tags, day count, window |
| `notes` | why this file exists and what it is meant to defeat |

`expected` uses the extraction contract's field keys plus `supplier_name`, which
is a top-level string in the response rather than a field entry.

## The OCR stress set

| File | What it tests | Target outcome |
|---|---|---|
| `01-degraded/...-rotated.pdf` | 1.8° skew | full read after deskew |
| `01-degraded/...-low-contrast.pdf` | washed-out photocopy | full read after binarisation |
| `01-degraded/...-photocopy.pdf` | speckle and streak lines | full read |
| `01-degraded/...-stamp-over-total.pdf` | a stamp over the totals | full read |
| `01-degraded/...-cropped-total.pdf` | amounts column cut off | `amount: null` |
| `02-photos/...-phone-photo.jpg` | tilt, shadow, JPEG q48 | full read |
| `02-photos/...-phone-photo-low-light.jpg` | brightness 0.72, contrast 0.75 | full read or explicit low confidence |
| `03-multipage/INV-2026-MP01.pdf` | 30 items, total on the last page | total from the final page |
| `04-edge-cases/INV-2026-EDGE01-ambiguous-dates.pdf` | `10/03/2026`, `04/05/2026` | Indian reading plus `DATE_ORDER_ASSUMED` |
| `04-edge-cases/INV-2026-EDGE02-no-total.pdf` | no Grand Total line | `amount: null` |
| `04-edge-cases/INV-2026-EDGE03-no-gstin.pdf` | no GSTIN | both GSTINs `null` |
| `05-chats/chat_ios_format.txt` | iOS export header | parsed as a chat |
| `05-chats/chat_hinglish.txt` | Hinglish, English-only tagger | `NO_CANDIDATES`, missing anchor |
| `05-chats/chat_group_continuation.txt` | system line and a wrapped message | wrapped line joined, system line ignored |

## Known gaps

- **No Devanagari or Kannada script.** The generator uses Helvetica, which has
  no Indic glyphs, and reportlab does not shape complex scripts. A bilingual
  invoice would need a shaped font (for example Noto Sans Devanagari) and a
  shaping engine. Not attempted rather than faked.
- **No handwriting.** Every signature line is typed text. A real corpus should
  add phone photos of signed GRNs and stamped challans.
- **No real Udyam certificate.** Deliberate, see the safety rules.
- **Hinglish is a negative control.** The expected answer is "no tags", which
  documents a limitation of the English keyword tagger. Do not "fix" it by
  making the tagger guess.
- **One invoice per case.** Consolidated statements, debit notes, credit notes
  and TDS certificates are not in the corpus yet; the contract does not collect
  them.

## Adding to the corpus

1. Add the document to `generate_samples.py` from the content model, never by
   hand-editing a PDF. Money is `Decimal`, formatted with `inr()`.
2. Give it an `expected` block. If a value is genuinely absent, write `null`
   and add a note saying why the absence is the point.
3. Run the generator, then `verify_samples.py`. A red check means the document
   or the extractor is wrong, not the ground truth.
4. Update this README's tables if you add a new document type or degradation.
