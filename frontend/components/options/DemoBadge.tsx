"use client";

import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";

/**
 * Option 1 runs on simulated providers: say so wherever it appears (rule 16).
 * `compact` is the short "Demo" form for table rows and strips.
 */
export function DemoBadge({ compact = false }: { compact?: boolean }) {
  const { t } = useT();
  return (
    <span
      title={t("options.demo_hint")}
      className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full border border-dashed border-warn/50 bg-warn-wash px-2 text-[0.6875rem] font-medium uppercase tracking-wide text-warn"
    >
      <Icon name="info" className="h-3.5 w-3.5" />
      {t(compact ? "options.demo_badge_short" : "options.demo_badge")}
    </span>
  );
}
