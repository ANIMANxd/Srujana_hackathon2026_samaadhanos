"use client";

import type { ReactNode } from "react";
import { useT } from "@/lib/i18n";
import type { OptionCitation } from "@/lib/types";

/**
 * One side of the choice card: a title, one big number, one line on what
 * happens, one line on the cost, one action. A greyed column keeps its title
 * and shows `blocked` (the one-line reason) instead of the number and action.
 */
export function OptionColumn({
  id,
  title,
  badge,
  status,
  dimmed,
  numberLabel,
  number,
  what,
  cost,
  extra,
  action,
  blocked,
  notes,
  citations,
}: {
  id: string;
  title: string;
  /** DemoBadge on the Get paid early column. */
  badge?: ReactNode;
  /** Icon-plus-text status (In progress, Paused, Locked). */
  status?: ReactNode;
  dimmed: boolean;
  numberLabel: string;
  number: ReactNode;
  what: string;
  cost: string;
  /** Extra controls under the cost line (the date picker). */
  extra?: ReactNode;
  action?: ReactNode;
  blocked?: ReactNode;
  notes: string[];
  citations: OptionCitation[];
}) {
  const { t } = useT();
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={`flex scroll-mt-24 flex-col gap-4 p-5 sm:p-6 ${dimmed ? "bg-paper-sunk text-ink-600" : ""}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`${id}-title`} className="section-title">
          {title}
        </h3>
        <span className="flex flex-wrap items-center gap-2">
          {status}
          {badge}
        </span>
      </header>

      {blocked ? (
        blocked
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <p className="text-sm text-ink-600">{numberLabel}</p>
            <p className="font-mono text-2xl font-semibold tracking-tight text-ink-950 sm:text-[1.75rem]">{number}</p>
          </div>
          <p className="text-sm text-ink-800">{what}</p>
          <p className="text-sm text-ink-600">{cost}</p>
          {extra}
          {action && <div className="mt-auto pt-1">{action}</div>}
        </>
      )}

      {(notes.length > 0 || citations.length > 0) && (
        <details className="text-sm text-ink-700">
          <summary className="link cursor-pointer select-none">{t("options.why")}</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          {citations.length > 0 && (
            <p className="mt-2 text-xs text-ink-500">
              {t("options.sources")}: {citations.map((c) => `${c.source} (${c.ref})`).join("; ")}
            </p>
          )}
        </details>
      )}
    </section>
  );
}
