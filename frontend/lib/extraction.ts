// Upload review helpers over the contract's ExtractionResponse (B9). The
// backend reads plain text only: invoice or PO text, or a WhatsApp .txt export.
// Every value is machine-suggested; the owner confirms it before it is used.

import type { ExtractedField, ExtractionResponse } from "./types";

export const FIELD_KEYS = [
  "invoice_number",
  "invoice_date",
  "amount",
  "buyer_name",
  "buyer_gstin",
  "supplier_gstin",
  "delivery_date",
  "po_reference",
  "written_credit_days",
] as const;

export type FieldKey = (typeof FIELD_KEYS)[number];

/** Fields the owner must fill before Approve enables. */
export const REQUIRED_FIELDS: FieldKey[] = ["invoice_date", "amount", "buyer_name"];

/** A field on the review screen: the extractor's suggestion, or the owner's edit. */
export type ReviewField = ExtractedField & { edited: boolean };

const EMPTY: ExtractedField = {
  value: null,
  source_text: null,
  line: null,
  page: null,
  method: "missing",
  confidence: 0,
  machine_suggested: true,
};

export function reviewFields(res: ExtractionResponse): Record<FieldKey, ReviewField> {
  const out = {} as Record<FieldKey, ReviewField>;
  for (const key of FIELD_KEYS) out[key] = { ...EMPTY, ...(res.fields[key] ?? {}), edited: false };
  return out;
}

/** Accept text uploads only; the extractor refuses PDFs and images with a plain message. */
export function looksLikeText(file: File): boolean {
  const name = file.name.toLowerCase();
  return file.type.startsWith("text/") || name.endsWith(".txt");
}
