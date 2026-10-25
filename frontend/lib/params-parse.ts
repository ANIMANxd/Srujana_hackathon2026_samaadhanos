// Plain (non-client) module: URL state types and parsers usable on the server.

import type { Lang } from "./i18n/parse";

export type View = "supplier" | "cfo";

/** Draft stage open in the case screen's send drawer (?send=1|2|3), so a demo state is linkable. */
export type SendStage = 1 | 2 | 3;

export type UrlState = { lang: Lang; view: View; judge: boolean; send: SendStage | null };

type Raw = string | string[] | undefined;

export function parseView(raw: Raw): View {
  return raw === "cfo" ? "cfo" : "supplier";
}

export function parseJudge(raw: Raw): boolean {
  return raw === "1";
}

export function parseSend(raw: Raw): SendStage | null {
  return raw === "1" || raw === "2" || raw === "3" ? (Number(raw) as SendStage) : null;
}

/** Keeps lang, view and judge across links. `send` is never carried over; pass it explicitly to open the drawer. */
export function buildHref(path: string, state: UrlState, overrides: Partial<UrlState> = {}): string {
  const s = { ...state, send: null, ...overrides };
  const q = new URLSearchParams();
  if (s.lang !== "en") q.set("lang", s.lang);
  if (s.view !== "supplier") q.set("view", s.view);
  if (s.judge) q.set("judge", "1");
  if (s.send) q.set("send", String(s.send));
  const qs = q.toString();
  return qs ? `${path}?${qs}` : path;
}
