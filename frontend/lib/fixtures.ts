// Offline fixtures, synced from ../contracts/fixtures (engine output only),
// plus the extractor's own results for its synthetic demo texts.

import { RAW_ARTIFACTS, RAW_EXTRACTION_SAMPLES, RAW_FIXTURES } from "@/fixtures";
import type { ArtifactKind, CaseRequest, CaseResponse, ExtractionResponse } from "./types";

export type Fixture = { id: string; title: string; request: CaseRequest; response: CaseResponse | null };

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/** Light shape check so a broken fixture fails loudly instead of rendering junk. */
export function asRequest(v: unknown): CaseRequest | null {
  if (!isObject(v) || typeof v.case_id !== "string" || !isObject(v.transaction) || !isObject(v.supplier)) return null;
  return v as unknown as CaseRequest;
}

export function asResponse(v: unknown): CaseResponse | null {
  if (!isObject(v) || typeof v.case_id !== "string" || !isObject(v.jurisdiction) || !Array.isArray(v.warnings)) return null;
  return v as unknown as CaseResponse;
}

export function asExtraction(v: unknown): ExtractionResponse | null {
  if (!isObject(v) || !isObject(v.fields) || typeof v.kind !== "string") return null;
  return v as unknown as ExtractionResponse;
}

export const FIXTURES: Fixture[] = RAW_FIXTURES.flatMap((f) => {
  const request = asRequest(f.request);
  if (!request) return [];
  return [{ id: f.id, title: f.title, request, response: asResponse(f.response) }];
});

export function fixtureFor(id: string): Fixture | undefined {
  return FIXTURES.find((f) => f.id === id);
}

/** An engine-generated draft saved for an unedited preset (offline only). */
export function artifactFixture(id: string, kind: ArtifactKind): string | null {
  return RAW_ARTIFACTS.find((a) => a.id === id && a.kind === kind)?.markdown ?? null;
}

export type ExtractionSample = { name: string; text: string; response: ExtractionResponse };

/** Synthetic upload samples with the result the extractor generated for each. */
export const EXTRACTION_SAMPLES: ExtractionSample[] = RAW_EXTRACTION_SAMPLES.flatMap((s) => {
  const response = asExtraction(s.response);
  return response ? [{ name: s.name, text: s.text, response }] : [];
});
