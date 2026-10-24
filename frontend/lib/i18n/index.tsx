"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { en, type MessageKey } from "./en";
import { kn } from "./kn";
import type { Lang } from "./parse";

export type { Lang } from "./parse";
export type Vars = Record<string, string | number>;

const DICTS: Record<Lang, Partial<Record<MessageKey, string>>> = { en, kn };

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m));
}

function hasKey(key: string): key is MessageKey {
  return Object.prototype.hasOwnProperty.call(en, key);
}

/** Translate with English fallback. */
export function translate(lang: Lang, key: MessageKey, vars?: Vars): string {
  return interpolate(DICTS[lang][key] ?? en[key], vars);
}

type I18n = {
  lang: Lang;
  t: (key: MessageKey, vars?: Vars) => string;
  /** Translate an API code (e.g. a warning or rule code) by prefix, falling back to the API's own text. */
  tCode: (prefix: string, code: string, fallback: string, vars?: Vars) => string;
};

const I18nContext = createContext<I18n>({
  lang: "en",
  t: (key, vars) => translate("en", key, vars),
  tCode: (prefix, code, fallback, vars) => {
    const k = `${prefix}.${code}`;
    return hasKey(k) ? translate("en", k, vars) : fallback;
  },
});

export function I18nProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  const t = useCallback((key: MessageKey, vars?: Vars) => translate(lang, key, vars), [lang]);
  const tCode = useCallback(
    (prefix: string, code: string, fallback: string, vars?: Vars) => {
      const k = `${prefix}.${code}`;
      return hasKey(k) ? translate(lang, k, vars) : fallback;
    },
    [lang],
  );
  const value = useMemo(() => ({ lang, t, tCode }), [lang, t, tCode]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): I18n {
  return useContext(I18nContext);
}
