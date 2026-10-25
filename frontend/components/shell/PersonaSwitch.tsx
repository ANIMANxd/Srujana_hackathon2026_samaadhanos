"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState, type View } from "@/lib/params";

const VIEWS: View[] = ["supplier", "cfo"];

/**
 * Supplier / Buyer CFO switch. The persona lives in ?view= (AGENTS.md §5), so a
 * demo state can be linked; it also sets the shell's tone (globals.css).
 */
export function PersonaSwitch({ path }: { path: string }) {
  const { t } = useT();
  const href = useHref();
  const { view } = useUrlState();
  return (
    <div role="group" aria-label={t("case.view.label")} className="inline-flex self-start rounded-lg border border-rule bg-paper-sunk p-0.5 sm:self-auto">
      {VIEWS.map((v) => (
        <Link
          key={v}
          href={href(path, { view: v })}
          scroll={false}
          aria-current={view === v ? "page" : undefined}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            view === v ? "bg-paper-raised text-ink-950 shadow-[0_1px_2px_rgb(13_13_12/0.08)]" : "text-ink-500 hover:text-ink-950"
          }`}
        >
          {t(v === "supplier" ? "case.view.supplier" : "case.view.cfo")}
        </Link>
      ))}
    </div>
  );
}
