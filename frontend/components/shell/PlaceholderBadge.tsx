"use client";

import { useT } from "@/lib/i18n";

/** Golden rule 7: every placeholder number carries this visible label. */
export function PlaceholderBadge() {
  const { t } = useT();
  return (
    <span className="ml-1.5 inline-flex h-5 items-center rounded-full border border-dashed border-warn/50 bg-warn-wash px-1.5 align-middle font-sans text-[0.6875rem] font-medium uppercase tracking-wide text-warn">
      {t("badge.placeholder")}
    </span>
  );
}
