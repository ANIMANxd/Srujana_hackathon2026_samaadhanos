"use client";

import { useT } from "@/lib/i18n";
import type { RecoveryStatus } from "@/lib/recoveryFlow";
import { StatusIcon } from "./StatusIcon";

/** What the server says about a stage: prepared, or sent by the owner. Nothing for an untouched stage. */
export function RecoveryBadge({ status }: { status: RecoveryStatus }) {
  const { t } = useT();
  if (status === "sent") return <StatusIcon size="sm" tone="ok" label={t("recovery.sent")} />;
  if (status === "prepared") return <StatusIcon size="sm" tone="info" icon="doc" label={t("recovery.prepared")} />;
  return <StatusIcon size="sm" tone="info" icon="clock" label={t("recovery.not_prepared")} />;
}
