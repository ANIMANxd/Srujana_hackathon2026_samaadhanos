"use client";

// Persona, language and judge mode live in URL params so a demo state can be
// linked or reset (AGENTS.md §5). Links built with useHref keep them.

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { buildHref, type UrlState } from "./params-parse";

export type { CaseTab, SendStage, UrlState, View } from "./params-parse";

const ParamsContext = createContext<UrlState>({ lang: "en", view: "supplier", judge: false, send: null, tab: "overview" });

export function ParamsProvider({ value, children }: { value: UrlState; children: ReactNode }) {
  return <ParamsContext.Provider value={value}>{children}</ParamsContext.Provider>;
}

export function useUrlState(): UrlState {
  return useContext(ParamsContext);
}

export function useHref(): (path: string, overrides?: Partial<UrlState>) => string {
  const state = useUrlState();
  return useCallback((path: string, overrides?: Partial<UrlState>) => buildHref(path, state, overrides), [state]);
}
