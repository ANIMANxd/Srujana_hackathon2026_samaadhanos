"use client";

import { useState } from "react";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";

type Node = { id: string; label: string; date: string | null; meaning: string; emphasis?: "today" | "start" };

/**
 * Date + one word per node; the plain meaning of each date is one toggle away.
 * Horizontal on wide screens, vertical on phones. Every date is the engine's.
 */
export function StatuteTimeline({ response }: { response: CaseResponse }) {
  const { t } = useT();
  const [explain, setExplain] = useState(false);
  const tl = response.timeline;

  if (!tl) {
    return (
      <section aria-labelledby="timeline-title" className="panel p-6">
        <h2 id="timeline-title" className="section-title">{t("timeline.title")}</h2>
        <p className="mt-2 text-sm text-ink-600">{t("timeline.unavailable")}</p>
      </section>
    );
  }

  const nodes: Node[] = [
    { id: "delivery", label: t("timeline.delivery"), date: tl.delivery_date, meaning: t("timeline.delivery.meaning") },
    { id: "window", label: t("timeline.window"), date: tl.objection_window_end, meaning: t("timeline.window.meaning") },
    { id: "acceptance", label: t("timeline.acceptance"), date: tl.acceptance_date, meaning: t(`timeline.acceptance.${tl.objection_status}`) },
    { id: "due", label: t("timeline.due"), date: tl.due_date, meaning: t("timeline.due.meaning", { days: tl.applied_days ?? "—" }) },
    { id: "appointed", label: t("timeline.appointed"), date: tl.appointed_day, meaning: t("timeline.appointed.meaning"), emphasis: "start" },
    { id: "today", label: t("timeline.today"), date: response.calculation_date, meaning: t("timeline.today.meaning"), emphasis: "today" },
    {
      id: "limitation",
      label: t("timeline.limitation"),
      date: response.limitation.expiry,
      meaning: response.limitation.expiry ? t("timeline.limitation.meaning") : t("timeline.limitation.unknown"),
    },
  ];

  return (
    <section aria-labelledby="timeline-title" className="panel p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 id="timeline-title" className="section-title">{t("timeline.title")}</h2>
        <button type="button" className="btn btn-quiet min-h-8 text-xs" aria-expanded={explain} onClick={() => setExplain((v) => !v)}>
          {explain ? t("timeline.hide") : t("timeline.explain")}
          <Icon name="chevron-down" className={`h-3.5 w-3.5 transition-transform ${explain ? "rotate-180" : ""}`} />
        </button>
      </div>

      <ol className="mt-6 grid md:grid-cols-7">
        {nodes.map((n, i) => {
          const isToday = n.emphasis === "today";
          const isStart = n.emphasis === "start" && n.date !== null;
          return (
            <li key={n.id} className="relative flex gap-3 pb-5 md:flex-col md:gap-3 md:pb-0 md:pr-3">
              {i < nodes.length - 1 && (
                <span
                  aria-hidden="true"
                  className="absolute left-[4.5px] top-3 h-full w-px bg-rule-strong md:left-2.5 md:top-[4.5px] md:h-px md:w-full"
                />
              )}
              <span
                aria-hidden="true"
                className={`relative z-10 mt-1 h-2.5 w-2.5 shrink-0 rounded-full md:mt-0 ${
                  isToday
                    ? "bg-saffron-500 ring-4 ring-saffron-100"
                    : isStart
                      ? "bg-ink-950"
                      : n.date
                        ? "border border-ink-500 bg-paper-raised"
                        : "border border-dashed border-ink-300 bg-paper-raised"
                }`}
              />
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className={`text-xs ${isToday ? "font-medium text-saffron-ink" : "text-ink-500"}`}>{n.label}</span>
                <span className={`num text-sm ${n.date ? "text-ink-950" : "text-ink-300"}`}>
                  {n.date ? date(n.date) : t("timeline.pending_date")}
                </span>
                {explain && <span className="mt-1 text-xs leading-snug text-ink-600">{n.meaning}</span>}
              </div>
            </li>
          );
        })}
      </ol>

      {tl.late_complaints.length > 0 && (
        <div className="mt-6 flex flex-col gap-1.5 border-t border-rule pt-4">
          <p className="flex items-center gap-1.5 text-xs font-medium text-warn">
            <Icon name="clock" className="h-3.5 w-3.5" />
            {t("timeline.late_title")}
          </p>
          <ul className="flex flex-col gap-1 text-sm text-ink-700">
            {tl.late_complaints.map((c, i) => (
              <li key={`${c.date}-${i}`}>{t("timeline.late_item", { date: date(c.date), reason: c.reason })}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
