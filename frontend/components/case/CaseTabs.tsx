"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState, type CaseTab } from "@/lib/params";

const TABS: CaseTab[] = ["overview", "evidence"];

/** Overview / Evidence & timeline. Links, not buttons, so each tab has a URL (?tab=). */
export function CaseTabs({ caseId }: { caseId: string }) {
  const { t } = useT();
  const href = useHref();
  const { tab } = useUrlState();
  return (
    <nav aria-label={t("tab.label")} className="flex gap-6 border-b border-rule">
      {TABS.map((x) => (
        <Link
          key={x}
          href={href(`/case/${caseId}`, { tab: x })}
          scroll={false}
          aria-current={tab === x ? "page" : undefined}
          className={`-mb-px border-b-2 pb-2.5 text-sm font-medium transition-colors ${
            tab === x ? "border-ink-950 text-ink-950" : "border-transparent text-ink-500 hover:text-ink-950"
          }`}
        >
          {t(x === "overview" ? "tab.overview" : "tab.evidence")}
        </Link>
      ))}
    </nav>
  );
}
