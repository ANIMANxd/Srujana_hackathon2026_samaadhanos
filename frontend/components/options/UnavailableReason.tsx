"use client";

import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { Icon } from "../common/Icon";

/** One line saying why an option is off, and a way across to the other one. */
export function UnavailableReason({
  reason,
  otherHref,
  otherLabel,
}: {
  reason: string | null;
  /** In-page anchor of the other column. */
  otherHref: string;
  otherLabel: MessageKey;
}) {
  const { t } = useT();
  return (
    <p className="flex flex-col gap-1.5 text-sm text-ink-700">
      <span className="flex items-start gap-2">
        <Icon name="lock" className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
        <span>{reason ?? t("options.unavailable.fallback")}</span>
      </span>
      <a href={otherHref} className="link inline-flex items-center gap-1 pl-6">
        {t(otherLabel)}
        <Icon name="arrow-right" className="h-3.5 w-3.5" />
      </a>
    </p>
  );
}
