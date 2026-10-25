"use client";

import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Meaning } from "./Meaning";

type Row = {
  key: string;
  date: string | null;
  label: string;
  note?: string;
  kind?: "start" | "today" | "late" | "override";
};

/**
 * Every statutory date the engine returned, in date order, with its meaning
 * one line below. The invoice date is the only input shown (labelled as such).
 * Rows without a date (not fixed yet) follow at the end in their natural order.
 */
export function TimelineDetail({ request, response }: { request: CaseRequest; response: CaseResponse }) {
  const { t } = useT();
  const tl = response.timeline;
  const checkpoints = response.buyer_cost?.deferral.checkpoints ?? [];

  const rows: Row[] = [
    { key: "invoice", date: request.transaction.invoice_date, label: t("tl.invoice"), note: t("tl.invoice_note") },
  ];
  if (tl) {
    rows.push(
      { key: "delivery", date: tl.delivery_date, label: t("timeline.delivery"), note: t("timeline.delivery.meaning") },
      { key: "window", date: tl.objection_window_end, label: t("timeline.window"), note: t("timeline.window.meaning") },
      { key: "acceptance", date: tl.acceptance_date, label: t("timeline.acceptance"), note: t(`timeline.acceptance.${tl.objection_status}`) },
      { key: "due", date: tl.due_date, label: t("timeline.due"), note: t("timeline.due.meaning", { days: tl.applied_days ?? "—" }) },
      { key: "appointed", date: tl.appointed_day, label: t("timeline.appointed"), note: t("timeline.appointed.meaning"), kind: "start" },
    );
    tl.late_complaints.forEach((c, i) =>
      rows.push({ key: `late-${i}`, date: c.date, label: c.description ?? t("tl.late_flag"), note: c.reason, kind: "late" }),
    );
  }
  checkpoints.forEach((c) => rows.push({ key: `fy-${c.fy_end}`, date: c.fy_end, label: t("tl.fy_end"), note: t("tl.fy_end_note") }));
  rows.push({ key: "calc", date: response.calculation_date, label: t("timeline.today"), note: t("tl.calc_note"), kind: "today" });
  rows.push({
    key: "limitation",
    date: response.limitation.expiry,
    label: t("timeline.limitation"),
    note: response.limitation.expiry ? t("timeline.limitation.meaning") : t("timeline.limitation.unknown"),
  });

  // ISO dates order correctly as text; undated rows keep their place at the end.
  const dated = rows.filter((r) => r.date).sort((a, b) => (a.date as string).localeCompare(b.date as string));
  const undated = rows.filter((r) => !r.date);

  return (
    <section aria-labelledby="tl-title" className="panel flex flex-col gap-5 p-6">
      <h2 id="tl-title" className="section-title">{t("tl.title")}</h2>

      {tl?.clamped && (
        <div role="note" className="flex items-start gap-3 rounded-lg border border-warn/30 bg-warn-wash px-4 py-3 text-sm text-warn">
          <Icon name="warn" className="mt-0.5 h-4 w-4" />
          <p>
            <span className="font-medium">{t("tl.override")}: </span>
            {t("tl.override_note", { agreed: tl.agreed_days ?? "—", applied: tl.applied_days ?? "—" })}
          </p>
        </div>
      )}

      <ol className="flex flex-col">
        {[...dated, ...undated].map((r, i, all) => (
          <li key={r.key} className="relative grid grid-cols-[6.5rem_1.25rem_1fr] gap-x-3 pb-5 last:pb-0 sm:grid-cols-[8rem_1.25rem_1fr]">
            <span className={`num pt-px text-sm ${r.date ? "text-ink-950" : "text-ink-500"}`}>{r.date ? date(r.date) : t("timeline.pending_date")}</span>
            <span className="relative flex justify-center">
              {i < all.length - 1 && <span aria-hidden="true" className="absolute top-3 h-[calc(100%+0.25rem)] w-px bg-rule-strong" />}
              <span
                aria-hidden="true"
                className={`relative z-10 mt-1 h-2.5 w-2.5 rounded-full ${
                  r.kind === "today"
                    ? "bg-saffron-500 ring-4 ring-saffron-100"
                    : r.kind === "start" && r.date
                      ? "bg-ink-950"
                      : r.kind === "late"
                        ? "bg-warn"
                        : r.date
                          ? "border border-ink-500 bg-paper-raised"
                          : "border border-dashed border-ink-300 bg-paper-raised"
                }`}
              />
            </span>
            <div className="flex min-w-0 flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink-950">
                {r.label}
                {r.kind === "late" && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-warn-wash px-2 py-0.5 text-xs font-medium text-warn">
                    <Icon name="clock" className="h-3 w-3" />
                    {t("tl.late_flag")}
                  </span>
                )}
              </span>
              {r.note && <span className="text-sm text-ink-600">{r.note}</span>}
            </div>
          </li>
        ))}
      </ol>

      {tl && <Meaning block="timeline" code={tl.objection_status} />}
    </section>
  );
}
