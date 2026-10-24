// Server-side helper: turns a page's searchParams into the URL state the
// client screens use (persona, language, judge mode).

import { parseLang } from "./i18n/parse";
import { parseJudge, parseView, type UrlState } from "./params-parse";

export async function urlStateFrom(searchParams: Promise<Record<string, string | string[] | undefined>>): Promise<UrlState> {
  const sp = await searchParams;
  return { lang: parseLang(sp.lang), view: parseView(sp.view), judge: parseJudge(sp.judge) };
}
