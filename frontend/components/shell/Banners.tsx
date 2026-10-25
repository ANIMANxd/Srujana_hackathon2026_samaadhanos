"use client";

import type { ReactNode } from "react";
import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";
import type { Tone } from "@/lib/derive";
import { Icon, type IconName } from "../common/Icon";

const TONE: Record<Tone, string> = {
  ok: "border-ok/25 bg-ok-wash text-ok",
  warn: "border-warn/25 bg-warn-wash text-warn",
  block: "border-block/25 bg-block-wash text-block",
  info: "border-rule bg-paper-raised text-ink-700",
};

/** One slim line. The page's only banner style. */
export function Banner({
  tone,
  icon,
  message,
  children,
}: {
  tone: Tone;
  icon: IconName;
  message: MessageKey;
  children?: ReactNode;
}) {
  const { t } = useT();
  return (
    <div role="status" className={`flex flex-wrap items-center gap-x-2.5 gap-y-1 rounded-lg border px-3.5 py-2 text-sm ${TONE[tone]}`}>
      <Icon name={icon} className="h-4 w-4" />
      <p className="font-medium">{t(message)}</p>
      {children}
    </div>
  );
}

/**
 * Data-honesty notices for a case screen (F1). Offline is announced once in the
 * top bar; these cover what changes the meaning of the figures themselves.
 */
export function DataBanners({ placeholder, needsBackend }: { placeholder: boolean; needsBackend?: boolean }) {
  if (!placeholder && !needsBackend) return null;
  return (
    <div className="no-print flex flex-col gap-2">
      {needsBackend && <Banner tone="warn" icon="lock" message="banner.recompute" />}
      {placeholder && <Banner tone="warn" icon="warn" message="banner.placeholder" />}
    </div>
  );
}
