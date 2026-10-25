"use client";

import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";

/**
 * A three-sentence orientation for a first-time owner. Collapsed by default so
 * it does not compete with the claim, and built on native <details>/<summary>
 * so it is keyboard and screen-reader friendly without script.
 */
export function ReadingGuide() {
  const { t } = useT();
  return (
    <details className="no-print panel px-5 py-3 text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-ink-950 [&::-webkit-details-marker]:hidden">
        <Icon name="info" className="h-4 w-4 text-ink-500" />
        {t("help.summary")}
        <Icon name="chevron-down" className="chevron ml-auto h-4 w-4 text-ink-500 transition-transform" />
      </summary>
      <ul className="mt-3 flex flex-col gap-2 border-t border-rule pt-3 text-ink-700">
        <li>{t("help.claim")}</li>
        <li>{t("help.dates")}</li>
        <li>{t("help.next")}</li>
      </ul>
    </details>
  );
}
