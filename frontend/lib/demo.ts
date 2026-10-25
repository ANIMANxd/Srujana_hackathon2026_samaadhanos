// The 60-second demo script, as data only.
//
// This file describes links and copy keys. It never touches a request, calls
// the engine, or computes a number: the hint component can only navigate.
// Keeping it separate makes the sequence reviewable and testable (smoke checks
// every step renders) without reading component code.

import type { MessageKey } from "./i18n/en";
import type { View } from "./params-parse";

export type DemoStep = {
  /** 1-based position shown as "Step n of 4". */
  n: number;
  /** Preset id, so the fixture check knows which saved engine output this step needs. */
  caseId: string;
  /** Paths that count as this step (the eligibility panel is the same content). */
  paths: readonly string[];
  /** null = either persona is on-script for this case. */
  view: View | null;
  titleKey: MessageKey;
  hintKey: MessageKey;
};

export const DEMO_START_CASE = "case_01";

export const DEMO_STEPS: readonly DemoStep[] = [
  {
    n: 1,
    caseId: "case_01",
    paths: ["/case/case_01"],
    view: "supplier",
    titleKey: "demo.1.title",
    hintKey: "demo.1.hint",
  },
  {
    n: 2,
    caseId: "case_01",
    paths: ["/case/case_01"],
    view: "cfo",
    titleKey: "demo.2.title",
    hintKey: "demo.2.hint",
  },
  {
    n: 3,
    caseId: "case_02",
    paths: ["/case/case_02"],
    view: null,
    titleKey: "demo.3.title",
    hintKey: "demo.3.hint",
  },
  {
    n: 4,
    caseId: "case_05a",
    paths: ["/case/case_05a", "/eligibility/case_05a"],
    view: null,
    titleKey: "demo.4.title",
    hintKey: "demo.4.hint",
  },
];

export const DEMO_TOTAL = DEMO_STEPS.length;

/** Index into DEMO_STEPS, or -1 when the current URL is off the scripted path. */
export function demoStepIndex(pathname: string, view: View): number {
  const path = pathname.replace(/\/+$/, "") || "/";
  return DEMO_STEPS.findIndex((s) => s.paths.includes(path) && (s.view === null || s.view === view));
}
