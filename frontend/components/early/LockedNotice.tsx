"use client";

import { date as fmtDate } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";
import { DemoBadge } from "../options/DemoBadge";

/** After signing the receivable belongs to the financier, so recovery is off for this invoice. */
export function LockedNotice({ dueDate }: { dueDate: string | null }) {
  const { t } = useT();
  return (
    <div className="flex items-start gap-3 rounded-lg border border-rule bg-paper-sunk px-4 py-3">
      <Icon name="lock" className="mt-0.5 h-4 w-4 shrink-0 text-ink-600" />
      <div className="flex flex-col gap-0.5 text-sm">
        <p className="flex flex-wrap items-center gap-2 font-medium text-ink-950">
          {t("early.locked.title")}
          <DemoBadge compact />
        </p>
        <p className="text-ink-700">{dueDate ? t("early.locked.body", { due: fmtDate(dueDate) }) : t("early.locked.body_nodate")}</p>
      </div>
    </div>
  );
}
