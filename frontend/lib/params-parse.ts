// Plain (non-client) module: URL state types and parsers usable on the server.

import type { Lang } from "./i18n/parse";

export type View = "supplier" | "cfo";

export type UrlState = { lang: Lang; view: View; judge: boolean };

type Raw = string | string[] | undefined;

export function parseView(raw: Raw): View {
  return raw === "cfo" ? "cfo" : "supplier";
}

export function parseJudge(raw: Raw): boolean {
  return raw === "1";
}

export function buildHref(path: string, state: UrlState, overrides: Partial<UrlState> = {}): string {
  const s = { ...state, ...overrides };
  const q = new URLSearchParams();
  if (s.lang !== "en") q.set("lang", s.lang);
  if (s.view !== "supplier") q.set("view", s.view);
  if (s.judge) q.set("judge", "1");
  const qs = q.toString();
  return qs ? `${path}?${qs}` : path;
}
