"use client";

import Link from "next/link";
import { daysBetween } from "@/lib/derive";
import { trackChip } from "@/lib/dueChip";
import { count, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import type { CaseSummary } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";

/** Same columns as the sample rows, so both kinds line up in one table. */
export const GRID =
  "md:grid-cols-[minmax(0,2fr)_minmax(0,1.8fr)_minmax(0,0.75fr)_minmax(0,1.05fr)_minmax(0,1.4fr)_1.25rem]";

/** One stored case: amount, days overdue or "due in N days", and where its track stands. */
export function CaseRow({ row }: { row: CaseSummary }) {
  const { t } = useT();
  const href = useHref();
  const chip = trackChip(row.active_track);
  const days = row.days_overdue ?? 0;
  const dueIn = row.due_date ? daysBetween(row.calculation_date, row.due_date) : null;
  const stage = row.stage && row.stage >= 1 && row.stage <= 4 ? row.stage : null;

  return (
    <li>
      <Link
        href={href(`/case/${row.id}`)}
        className={`group grid grid-cols-2 items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-paper ${GRID}`}
      >
        <div className="col-span-2 flex min-w-0 flex-col gap-0.5 md:col-span-1">
          <span className="truncate font-medium text-ink-950">{t("dues.row.invoice", { no: row.invoice_no })}</span>
          <span className="num truncate text-xs text-ink-500">{row.buyer_gstin ?? row.supplier_ref}</span>
        </div>

        <div className="col-span-2 min-w-0 md:col-span-1">
          <span className="sr-only">{t("dues.col.track")}: </span>
          <span className="inline-flex max-w-full flex-wrap items-center gap-x-1 text-sm">
            <StatusIcon
              size="sm"
              wrap
              tone={chip.tone}
              icon={chip.icon}
              label={chip.prefix ? `${t(chip.prefix)} · ${t(chip.status as MessageKey, chip.vars)}` : t(chip.status as MessageKey)}
            />
          </span>
        </div>

        <div className="num min-w-0 text-sm">
          <span className="sr-only">{t("dues.col.overdue")}: </span>
          {days > 0 ? (
            <span className="inline-flex items-start gap-1.5 text-warn">
              <Icon name="clock" className="mt-0.5 h-3.5 w-3.5" />
              {t("dues.row.overdue", { n: count(days) })}
            </span>
          ) : dueIn === null ? (
            <span className="text-ink-500">{t("dues.row.no_date")}</span>
          ) : dueIn <= 0 ? (
            <span className="text-ink-600">{t("dues.row.due_today")}</span>
          ) : (
            <span className="text-ink-600">{t(dueIn === 1 ? "dues.row.due_in_one" : "dues.row.due_in", { n: count(dueIn) })}</span>
          )}
        </div>

        <div className="min-w-0 text-sm md:text-right">
          <span className="sr-only">{t("dues.col.amount")}: </span>
          <span className="figure font-medium text-ink-950">{money(row.accepted_amount)}</span>
        </div>

        <div className="col-span-2 min-w-0 text-sm text-ink-700 md:col-span-1">
          <span className="sr-only">{t("dues.col.stage")}: </span>
          {stage && (
            <span className="line-clamp-2 leading-snug">
              <span className="num mr-1.5 text-xs text-ink-500">{stage}</span>
              {t(`stage.${stage}.title` as MessageKey)}
            </span>
          )}
        </div>

        <Icon name="chevron" className="hidden h-4 w-4 text-ink-500 transition-colors group-hover:text-ink-950 md:block" />
      </Link>
    </li>
  );
}
