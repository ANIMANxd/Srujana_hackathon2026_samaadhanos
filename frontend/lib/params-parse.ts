// Plain (non-client) module: URL state types and parsers usable on the server.

import type { Lang } from "./i18n/parse";

export type View = "supplier" | "cfo";

/** Draft stage open in the case screen's send drawer (?send=1|2|3), so a demo state is linkable. */
export type SendStage = 1 | 2 | 3;

/** Case screen tab (?tab=evidence), linkable like the rest of the demo state. */
export type CaseTab = "overview" | "evidence";

export type UrlState = { lang: Lang; view: View; judge: boolean; send: SendStage | null; tab: CaseTab };

type Raw = string | string[] | undefined;

export function parseView(raw: Raw): View {
  return raw === "cfo" ? "cfo" : "supplier";
}

export function parseJudge(raw: Raw): boolean {
  return raw === "1";
}

export function parseTab(raw: Raw): CaseTab {
  return raw === "evidence" ? "evidence" : "overview";
}

export function parseSend(raw: Raw): SendStage | null {
  return raw === "1" || raw === "2" || raw === "3" ? (Number(raw) as SendStage) : null;
}

/** Keeps lang, view and judge across links. `send` and `tab` are never carried over; pass them explicitly. */
export function buildHref(path: string, state: UrlState, overrides: Partial<UrlState> = {}): string {
  const s = { ...state, send: null, tab: "overview" as CaseTab, ...overrides };
  const q = new URLSearchParams();
  if (s.lang !== "en") q.set("lang", s.lang);
  if (s.view !== "supplier") q.set("view", s.view);
  if (s.judge) q.set("judge", "1");
  if (s.tab !== "overview") q.set("tab", s.tab);
  if (s.send) q.set("send", String(s.send));
  const qs = q.toString();
  return qs ? `${path}?${qs}` : path;
}
