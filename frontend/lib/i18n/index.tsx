"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { en, type MessageKey } from "./en";
import { kn, knWarningMap } from "./kn";
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

/**
 * Read the case-specific details an engine warning's English sentence carries.
 * Returns null when a required detail is absent, so the caller can show the
 * engine's own sentence rather than a translation with a fact missing.
 */
function warningVars(code: string, text: string): Vars | null {
  if (code === "UNVERIFIED_CONSTANT") {
    const m = /Constant '([^']+)'.*?\(source '([^']+)'\)/.exec(text);
    return m ? { key: m[1], source: m[2] } : null;
  }
  if (code === "POTENTIAL_ACKNOWLEDGMENT") {
    const m = /\((\d{4}-\d{2}-\d{2})\)/.exec(text);
    return m ? { date: m[1] } : null;
  }
  return {};
}

/**
 * Translate an engine warning by code (architecture §8.3). English always shows
 * the backend's own text. Kannada uses kn.ts when the code is covered, and
 * falls back to the English sentence when it is not, or when the details the
 * Kannada sentence needs cannot be read from it.
 */
export function translateWarning(lang: Lang, code: string, fallback: string): string {
  if (lang === "en") return fallback;
  const entry = knWarningMap[code];
  if (!entry) return fallback;
  const vars = warningVars(code, fallback);
  if (!vars || entry.needsVars.some((name) => !(name in vars))) return fallback;
  return interpolate(entry.kn, vars);
}

type I18n = {
  lang: Lang;
  t: (key: MessageKey, vars?: Vars) => string;
  /** Translate an API code (e.g. a warning or rule code) by prefix, falling back to the API's own text. */
  tCode: (prefix: string, code: string, fallback: string, vars?: Vars) => string;
  /** Translate an engine warning by code, keeping the engine's own English text as the fallback. */
  tWarning: (code: string, fallback: string) => string;
};

const I18nContext = createContext<I18n>({
  lang: "en",
  t: (key, vars) => translate("en", key, vars),
  tCode: (prefix, code, fallback, vars) => {
    const k = `${prefix}.${code}`;
    return hasKey(k) ? translate("en", k, vars) : fallback;
  },
  tWarning: (code, fallback) => translateWarning("en", code, fallback),
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
  const tWarning = useCallback((code: string, fallback: string) => translateWarning(lang, code, fallback), [lang]);
  const value = useMemo(() => ({ lang, t, tCode, tWarning }), [lang, t, tCode, tWarning]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): I18n {
  return useContext(I18nContext);
}
