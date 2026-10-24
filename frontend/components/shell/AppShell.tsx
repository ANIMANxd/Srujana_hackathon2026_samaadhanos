"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { I18nProvider, useT } from "@/lib/i18n";
import { ParamsProvider, useHref, type UrlState } from "@/lib/params";
import { Icon } from "../common/Icon";

function TopNav() {
  const { t } = useT();
  const href = useHref();
  return (
    <header className="no-print border-b border-rule bg-paper-raised">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href={href("/")} className="group flex items-baseline gap-2">
          <span className="font-display text-xl font-bold tracking-tight text-ink-950">{t("app.name")}</span>
          <span className="hidden text-sm text-ink-500 md:inline">{t("app.tagline")}</span>
        </Link>
        <nav aria-label={t("nav.main")} className="flex items-center gap-2">
          <Link href={href("/")} className="btn btn-quiet">
            {t("nav.dues")}
          </Link>
          <Link href={href("/upload")} className="btn btn-primary min-h-10 px-3.5" aria-label={t("nav.upload")}>
            <Icon name="upload" className="h-4 w-4" />
            <span className="hidden sm:inline">{t("nav.upload")}</span>
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  const { t } = useT();
  return (
    <footer className="border-t border-rule">
      <p className="mx-auto max-w-6xl px-4 py-5 text-sm text-ink-600 sm:px-6">{t("footer.disclaimer")}</p>
    </footer>
  );
}

function SkipLink() {
  const { t } = useT();
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-ink-900 focus:px-4 focus:py-2 focus:text-paper"
    >
      {t("app.skip")}
    </a>
  );
}

/** Wraps every screen: URL state, i18n, top nav, footer. */
export function AppShell({ state, children }: { state: UrlState; children: ReactNode }) {
  return (
    <ParamsProvider value={state}>
      <I18nProvider lang={state.lang}>
        <div className="flex min-h-screen flex-col">
          <SkipLink />
          <TopNav />
          <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
            {children}
          </main>
          <Footer />
        </div>
      </I18nProvider>
    </ParamsProvider>
  );
}
