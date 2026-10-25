"use client";

import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";

/** Option 1 runs on simulated providers: say so on the column itself (rule 16). */
export function DemoBadge() {
  const { t } = useT();
  return (
    <span
      title={t("options.demo_hint")}
      className="inline-flex h-6 items-center gap-1 rounded-full border border-dashed border-warn/50 bg-warn-wash px-2 text-[0.6875rem] font-medium uppercase tracking-wide text-warn"
    >
      <Icon name="info" className="h-3.5 w-3.5" />
      {t("options.demo_badge")}
    </span>
  );
}
