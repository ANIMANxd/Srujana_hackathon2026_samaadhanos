"use client";

import { eligibilityTone } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import type { JurisdictionStatus } from "@/lib/types";
import { StatusIcon } from "../common/StatusIcon";

export function EligibilityPill({ status }: { status: JurisdictionStatus }) {
  const { t } = useT();
  return <StatusIcon tone={eligibilityTone(status)} label={t(`eligibility.${status}`)} />;
}
