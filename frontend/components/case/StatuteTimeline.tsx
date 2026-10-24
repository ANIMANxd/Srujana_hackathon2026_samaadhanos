"use client";

import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";

type Node = { id: string; label: string; date: string | null; meaning: string; emphasis?: "today" | "start" };

/** Horizontal on wide screens, vertical on phones. Every date comes from the engine. */
export function StatuteTimeline({ response }: { response: CaseResponse }) {
  const { t } = useT();
  const tl = response.timeline;

  if (!tl) {
    return (
      <section aria-labelledby="timeline-title" className="panel p-5">
        <h2 id="timeline-title" className="ledger-rule font-display text-xl font-semibold">
          {t("timeline.title")}
        </h2>
        <p className="mt-3 text-ink-700">{t("timeline.unavailable")}</p>
      </section>
    );
  }

  const nodes: Node[] = [
    { id: "delivery", label: t("timeline.delivery"), date: tl.delivery_date, meaning: t("timeline.delivery.meaning") },
    { id: "window", label: t("timeline.window"), date: tl.objection_window_end, meaning: t("timeline.window.meaning") },
    {
      id: "acceptance",
      label: t("timeline.acceptance"),
      date: tl.acceptance_date,
      meaning: t(`timeline.acceptance.${tl.objection_status}`),
    },
    {
      id: "due",
      label: t("timeline.due"),
      date: tl.due_date,
      meaning: t("timeline.due.meaning", { days: tl.applied_days ?? "—" }),
    },
    {
      id: "appointed",
      label: t("timeline.appointed"),
      date: tl.appointed_day,
      meaning: t("timeline.appointed.meaning"),
      emphasis: "start",
    },
    {
      id: "today",
      label: t("timeline.today"),
      date: response.calculation_date,
      meaning: t("timeline.today.meaning"),
      emphasis: "today",
    },
    {
      id: "limitation",
      label: t("timeline.limitation"),
      date: response.limitation.expiry,
      meaning: response.limitation.expiry ? t("timeline.limitation.meaning") : t("timeline.limitation.unknown"),
    },
  ];

  return (
    <section aria-labelledby="timeline-title" className="panel p-5">
      <h2 id="timeline-title" className="ledger-rule font-display text-xl font-semibold text-ink-950">
        {t("timeline.title")}
      </h2>

      <ol className="mt-5 grid gap-0 md:grid-cols-7">
        {nodes.map((n, i) => {
          const isToday = n.emphasis === "today";
          const isStart = n.emphasis === "start";
          return (
            <li key={n.id} className="relative flex gap-3 pb-5 md:flex-col md:gap-2 md:pb-0 md:pr-2">
              {/* connector rule */}
              {i < nodes.length - 1 && (
                <span
                  aria-hidden="true"
                  className="absolute left-[7px] top-4 h-full w-px bg-rule-strong md:left-4 md:top-[7px] md:h-px md:w-full"
                />
              )}
              <span
                aria-hidden="true"
                className={`relative z-10 mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full border-2 ${
                  isToday
                    ? "border-saffron-600 bg-saffron-500"
                    : isStart
                      ? "border-ink-900 bg-ink-900"
                      : n.date
                        ? "border-ink-700 bg-paper-raised"
                        : "border-dashed border-ink-300 bg-paper"
                }`}
              />
              <div className="flex flex-col">
                <span className={`text-sm font-semibold ${isToday ? "text-saffron-ink" : "text-ink-900"}`}>{n.label}</span>
                <span className="num text-sm text-ink-800">{n.date ? date(n.date) : t("timeline.pending_date")}</span>
                <span className="mt-0.5 text-xs leading-snug text-ink-600">{n.meaning}</span>
              </div>
            </li>
          );
        })}
      </ol>

      {(tl.clamped || tl.late_complaints.length > 0) && (
        <div className="mt-5 flex flex-col gap-2 border-t border-rule pt-4">
          {tl.clamped && (
            <p className="flex flex-wrap items-center gap-2 text-sm">
              <StatusIcon
                tone="warn"
                size="sm"
                label={t("timeline.clamped", { agreed: tl.agreed_days ?? "—", applied: tl.applied_days ?? "—" })}
              />
            </p>
          )}
          {tl.late_complaints.length > 0 && (
            <div>
              <p className="flex items-center gap-1.5 text-sm font-semibold text-warn">
                <Icon name="clock" className="h-4 w-4" />
                {t("timeline.late_title")}
              </p>
              <ul className="mt-1 list-disc pl-6 text-sm text-ink-700">
                {tl.late_complaints.map((c, i) => (
                  <li key={`${c.date}-${i}`}>{t("timeline.late_item", { date: date(c.date), reason: c.reason })}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
