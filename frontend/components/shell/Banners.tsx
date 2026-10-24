"use client";

import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";
import type { Tone } from "@/lib/derive";
import { Icon, type IconName } from "../common/Icon";

const TONE: Record<Tone, string> = {
  ok: "border-ok/40 bg-ok-wash text-ok",
  warn: "border-warn/40 bg-warn-wash text-warn",
  block: "border-block/40 bg-block-wash text-block",
  info: "border-info/40 bg-info-wash text-info",
};

export function Banner({ tone, icon, message }: { tone: Tone; icon: IconName; message: MessageKey }) {
  const { t } = useT();
  return (
    <div role="status" className={`flex items-start gap-2.5 rounded-md border px-4 py-2.5 text-sm font-medium ${TONE[tone]}`}>
      <Icon name={icon} className="mt-0.5 h-4 w-4" />
      <p>{t(message)}</p>
    </div>
  );
}

/** The data-honesty banners every case screen shows when they apply (F1). */
export function DataBanners({
  offline,
  placeholder,
  needsBackend,
}: {
  offline: boolean;
  placeholder: boolean;
  needsBackend?: boolean;
}) {
  if (!offline && !placeholder && !needsBackend) return null;
  return (
    <div className="no-print flex flex-col gap-2">
      {offline && !needsBackend && <Banner tone="info" icon="info" message="banner.offline" />}
      {needsBackend && <Banner tone="warn" icon="lock" message="banner.recompute" />}
      {placeholder && <Banner tone="warn" icon="warn" message="banner.placeholder" />}
    </div>
  );
}
