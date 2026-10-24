// Invoice extraction (prompt B9-lite / F12). The endpoint and its types are NOT
// in contract v1.0 yet, so the shape below is a frontend-local mirror of the
// B9-lite prompt. Replace it with the generated type once the backend adds
// /api/v1/extract-evidence to the contract (CONTRACT-REQUESTS.md, CR-4).

import sample from "@/demo-cases/invoice_sample.extraction.json";
import { ApiError } from "./api";

export type ExtractionMethod = "regex" | "llm" | "missing" | "manual";

export type ExtractedField = {
  value: string | null;
  source_text: string | null;
  page: number | null;
  method: ExtractionMethod;
  confidence: number;
};

export const FIELD_KEYS = [
  "invoice_number",
  "invoice_date",
  "amount",
  "supplier_gstin",
  "buyer_gstin",
  "buyer_name",
  "delivery_date",
  "po_reference",
] as const;

export type FieldKey = (typeof FIELD_KEYS)[number];

/** Fields the owner must fill before Approve enables. */
export const REQUIRED_FIELDS: FieldKey[] = ["invoice_date", "amount", "buyer_name"];

export type Extraction = {
  fields: Record<FieldKey, ExtractedField>;
  supplier_name: string | null;
  placeholder: boolean;
};

function normalise(raw: unknown, placeholder: boolean): Extraction | null {
  if (typeof raw !== "object" || raw === null || !("fields" in raw)) return null;
  const src = (raw as { fields: Record<string, Partial<ExtractedField>> }).fields;
  const fields = {} as Record<FieldKey, ExtractedField>;
  for (const key of FIELD_KEYS) {
    const f = src[key] ?? {};
    const method: ExtractionMethod =
      f.method === "regex" || f.method === "llm" || f.method === "manual" ? f.method : "missing";
    fields[key] = {
      value: typeof f.value === "string" ? f.value : null,
      source_text: typeof f.source_text === "string" ? f.source_text : null,
      page: typeof f.page === "number" ? f.page : null,
      method: typeof f.value === "string" ? method : "missing",
      confidence: typeof f.confidence === "number" ? f.confidence : 0,
    };
  }
  const supplier = (raw as { supplier_name?: unknown }).supplier_name;
  return { fields, supplier_name: typeof supplier === "string" ? supplier : null, placeholder };
}

export function sampleExtraction(): Extraction {
  const e = normalise(sample, true);
  if (!e) throw new Error("invoice_sample.extraction.json is malformed");
  return e;
}

/** Returns null when the endpoint does not exist yet or the backend is down. */
export async function extractEvidence(file: File): Promise<Extraction | null> {
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await fetch("/api/v1/extract-evidence", { method: "POST", body: form });
  } catch {
    return null;
  }
  if (res.status === 404 || res.status === 405 || res.status >= 500) return null;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    return null;
  }
  if (!res.ok) {
    const msg =
      typeof body === "object" && body !== null && "error" in body
        ? String((body as { error: { message?: unknown } }).error.message ?? "")
        : "";
    throw new ApiError(res.status, "EXTRACTION_FAILED", msg || "The invoice could not be read.");
  }
  return normalise(body, false);
}

