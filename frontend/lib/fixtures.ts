// Offline fixtures, synced from ../contracts/fixtures (engine output only) plus
// the demo request files in ../demo-cases (INPUT only, never outputs).

import { RAW_FIXTURES } from "@/fixtures";
import demo02 from "@/demo-cases/demo_02.request.json";
import demo03 from "@/demo-cases/demo_03.request.json";
import type { CaseRequest, CaseResponse } from "./types";

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

export const FIXTURES: Fixture[] = RAW_FIXTURES.flatMap((f) => {
  const request = asRequest(f.request);
  if (!request) return [];
  return [{ id: f.id, title: f.title, request, response: asResponse(f.response) }];
});

export function fixtureFor(id: string): Fixture | undefined {
  return FIXTURES.find((f) => f.id === id);
}

export type DemoCase = { id: string; title: string; request: CaseRequest };

type DemoFile = { title: string; request: unknown };

/** Synthetic demo inputs used until the backend ships more presets (B7). */
export const DEMO_CASES: DemoCase[] = ([demo02, demo03] as DemoFile[]).flatMap((d) => {
  const request = asRequest(d.request);
  return request ? [{ id: request.case_id, title: d.title, request }] : [];
});

export function demoFor(id: string): DemoCase | undefined {
  return DEMO_CASES.find((d) => d.id === id);
}
