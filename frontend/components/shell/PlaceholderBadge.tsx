"use client";

import { useT } from "@/lib/i18n";

/** Golden rule 7: every placeholder number carries this visible label. */
export function PlaceholderBadge() {
  const { t } = useT();
  return (
    <span className="ml-1 inline-block rounded-sm border border-dashed border-warn/60 bg-warn-wash px-1 py-px align-middle font-sans text-[0.6875rem] font-semibold uppercase tracking-wide text-warn">
      {t("badge.placeholder")}
    </span>
  );
}
