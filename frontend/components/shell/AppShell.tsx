"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { I18nProvider, useT } from "@/lib/i18n";
import { ParamsProvider, useHref, type UrlState } from "@/lib/params";
import { JUDGE_EVENT, useConnection } from "@/lib/useConnection";
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

/** Connection to the engine: the one place the offline state is announced. */
function ConnectionPill() {
  const { t } = useT();
  const conn = useConnection();
  const label = conn === "live" ? t("conn.live") : conn === "offline" ? t("conn.offline") : t("conn.checking");
  const hint = conn === "live" ? t("conn.live_hint") : conn === "offline" ? t("conn.offline_hint") : undefined;
  return (
    <span
      role="status"
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

function TopNav() {
  const { t } = useT();
  const href = useHref();
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
          <ConnectionPill />
          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event(JUDGE_EVENT))}
            className="btn btn-quiet min-h-8 px-2 text-xs"
            title={t("judge.hint")}
          >
            <span className="num rounded border border-rule px-1 text-[0.6875rem] text-ink-500" aria-hidden="true">⌃J</span>
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

/** Wraps every screen: URL state, i18n, top bar, footer. */
export function AppShell({ state, children }: { state: UrlState; children: ReactNode }) {
  return (
    <ParamsProvider value={state}>
      <I18nProvider lang={state.lang}>
        <div className="flex min-h-screen flex-col">
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
