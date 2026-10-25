"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { I18nProvider, useT } from "@/lib/i18n";
import { ParamsProvider, useHref, useUrlState, type UrlState } from "@/lib/params";
import { JUDGE_EVENT, useConnection, type Connection } from "@/lib/useConnection";
import { Icon } from "../common/Icon";

function Wordmark() {
  const { t } = useT();
  const href = useHref();
  return (
    <Link href={href("/")} className="flex items-center gap-2.5" aria-label={t("app.name")}>
      <span aria-hidden="true" className="relative grid h-6 w-6 place-items-center rounded-[7px] bg-ink-950">
        <span className="h-2 w-2 rounded-full bg-saffron-500" />
      </span>
      <span className="text-[0.9375rem] font-semibold tracking-[-0.01em] text-ink-950">{t("app.name")}</span>
    </Link>
  );
}

/** Compact engine status next to the language toggle. */
function ConnectionPill({ conn }: { conn: Connection }) {
  const { t } = useT();
  const label = conn === "live" ? t("conn.live") : conn === "offline" ? t("conn.offline") : t("conn.checking");
  const hint = conn === "live" ? t("conn.live_hint") : conn === "offline" ? t("conn.offline_hint") : undefined;
  return (
    <span
      title={hint}
      className={`inline-flex h-7 items-center gap-2 rounded-full border px-2.5 text-xs font-medium ${
        conn === "offline" ? "border-warn/30 bg-warn-wash text-warn" : "border-rule bg-paper-raised text-ink-700"
      }`}
    >
      {conn === "offline" ? (
        <Icon name="warn" className="h-3.5 w-3.5" />
      ) : (
        <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${conn === "live" ? "bg-ok" : "bg-ink-300"}`} />
      )}
      <span className="hidden sm:inline">{label}</span>
      <span className="sr-only sm:hidden">{label}</span>
    </span>
  );
}

function NavLink({ to, children }: { to: string; children: ReactNode }) {
  const href = useHref();
  const path = usePathname();
  const active = to === "/" ? path === "/" || path.startsWith("/case") || path.startsWith("/eligibility") : path.startsWith(to);
  return (
    <Link
      href={href(to)}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors ${
        active ? "text-ink-950" : "text-ink-500 hover:text-ink-950"
      }`}
    >
      {children}
    </Link>
  );
}

/** ?lang= switch (architecture §10 LangToggle). Missing Kannada keys fall back to English. */
function LangToggle() {
  const { t, lang } = useT();
  const href = useHref();
  const { tab, send } = useUrlState();
  const path = usePathname();
  return (
    <div role="group" aria-label={t("nav.language")} className="inline-flex h-7 items-center rounded-full border border-rule bg-paper-raised p-0.5 text-xs">
      {(["en", "kn"] as const).map((l) => (
        <Link
          key={l}
          href={href(path, { lang: l, tab, send })}
          scroll={false}
          lang={l}
          aria-current={lang === l ? "true" : undefined}
          aria-label={t(l === "en" ? "lang.en" : "lang.kn")}
          className={`grid h-6 min-w-7 place-items-center rounded-full px-2 font-medium transition-colors ${
            lang === l ? "bg-ink-950 text-paper-raised" : "text-ink-500 hover:text-ink-950"
          }`}
        >
          {t(l === "en" ? "lang.en_short" : "lang.kn_short")}
        </Link>
      ))}
    </div>
  );
}

function TopNav() {
  const { t } = useT();
  const href = useHref();
  const conn = useConnection();
  return (
    <header className="no-print sticky top-0 z-40 border-b border-rule bg-paper-raised/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1120px] items-center justify-between gap-4 px-4 sm:px-8">
        <div className="flex items-center gap-6">
          <Wordmark />
          <nav aria-label={t("nav.main")} className="hidden items-center gap-1 sm:flex">
            <NavLink to="/">{t("nav.dues")}</NavLink>
            <NavLink to="/upload">{t("nav.upload")}</NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <LangToggle />
          <ConnectionPill conn={conn} />
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event(JUDGE_EVENT))}
            className="btn btn-quiet min-h-8 px-2 text-xs"
            title={t("judge.hint")}
          >
            <span className="num rounded border border-rule px-1 text-[0.6875rem] text-ink-500" aria-hidden="true">{t("judge.kbd")}</span>
            <span className="hidden md:inline">{t("nav.judge")}</span>
            <span className="sr-only md:hidden">{t("nav.judge")}</span>
          </button>
          <div className="flex sm:hidden">
            <Link href={href("/upload")} className="btn btn-secondary min-h-8 px-2.5" aria-label={t("nav.upload")}>
              <Icon name="upload" className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </div>
      {conn === "offline" && (
        // F1: persistent "Offline demo data" banner. It lives in the sticky top
        // bar so it stays on screen on every page while the backend is down.
        <div role="status" className="border-t border-warn/20 bg-warn-wash">
          <p className="mx-auto flex max-w-[1120px] items-center gap-2 px-4 py-1.5 text-xs font-medium text-warn sm:px-8">
            <Icon name="warn" className="h-3.5 w-3.5" />
            {t("banner.offline")}
          </p>
        </div>
      )}
    </header>
  );
}

function Footer() {
  const { t } = useT();
  return (
    <footer className="no-print border-t border-rule">
      <p className="mx-auto max-w-[1120px] px-4 py-6 text-xs leading-relaxed text-ink-500 sm:px-8">{t("footer.disclaimer")}</p>
    </footer>
  );
}

function SkipLink() {
  const { t } = useT();
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-ink-950 focus:px-4 focus:py-2 focus:text-paper-raised"
    >
      {t("app.skip")}
    </a>
  );
}

/** Keeps <html lang> in step with ?lang= so screen readers switch voice. */
function DocumentLang({ lang }: { lang: string }) {
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  return null;
}

/**
 * Wraps every screen: URL state, i18n, persona tone, top bar, footer.
 * The tone follows ?view= (supplier workspace or buyer CFO view; see globals.css).
 */
export function AppShell({ state, children }: { state: UrlState; children: ReactNode }) {
  return (
    <ParamsProvider value={state}>
      <I18nProvider lang={state.lang}>
        <DocumentLang lang={state.lang} />
        <div lang={state.lang} data-tone={state.view === "cfo" ? "cfo" : "supplier"} className="flex min-h-screen flex-col bg-paper">
          <SkipLink />
          <TopNav />
          <main id="main" className="mx-auto w-full max-w-[1120px] flex-1 px-4 py-8 sm:px-8 sm:py-10">
            {children}
          </main>
          <Footer />
        </div>
      </I18nProvider>
    </ParamsProvider>
  );
}
