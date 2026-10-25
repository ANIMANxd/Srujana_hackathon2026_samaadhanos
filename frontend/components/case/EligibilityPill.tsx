"use client";

import Link from "next/link";
import { eligibilityTone } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { JurisdictionStatus } from "@/lib/types";
import { Icon, type IconName } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";

/** One icon per gate outcome, so the five states differ by shape as well as colour. */
const STATUS_ICON: Record<JurisdictionStatus, IconName> = {
  ELIGIBLE: "ok",
  BARRED_SILPI: "lock",
  EXCLUDED_TRADER: "block",
  EXCLUDED_MEDIUM: "block",
  INSUFFICIENT_DATA: "open",
};

/**
 * jurisdiction.status as icon + text. Pass `caseId` to make every non-eligible
 * state a link to its explanation panel (/eligibility/[id]); leave it out where
 * the pill sits inside another link (the dues table) or on that panel itself.
 */
export function EligibilityPill({ status, caseId, wrap = false }: { status: JurisdictionStatus; caseId?: string; wrap?: boolean }) {
  const { t } = useT();
  const href = useHref();
  const pill = <StatusIcon size="sm" tone={eligibilityTone(status)} icon={STATUS_ICON[status]} label={t(`eligibility.${status}`)} wrap={wrap} />;
  if (!caseId || status === "ELIGIBLE") return pill;
  return (
    <Link
      href={href(`/eligibility/${caseId}`)}
      aria-label={`${t(`eligibility.${status}`)} · ${t("eligibility.see_why")}`}
      className="group inline-flex items-center gap-1 rounded-full"
    >
      {pill}
      <Icon name="chevron" className="h-3.5 w-3.5 text-ink-500 transition-colors group-hover:text-ink-950" />
    </Link>
  );
}
