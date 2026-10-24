"use client";

import { useState } from "react";
import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";
import { configEntry, configText } from "@/lib/useConfig";
import type { StatuteConfig } from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { StatusIcon } from "../common/StatusIcon";

export type ChipId = "s16" | "s2b" | "s15";

/** Which statute-config keys each explanation reads its numbers from. */
const CHIP_KEYS: Record<ChipId, { vars: Record<string, string>; ref: MessageKey; plain: MessageKey }> = {
  s16: { vars: { multiplier: "interest_multiplier" }, ref: "chip.s16.ref", plain: "chip.s16.plain" },
  s2b: { vars: { days: "objection_window_days" }, ref: "chip.s2b.ref", plain: "chip.s2b.plain" },
  s15: { vars: { cap: "credit_cap_days", none: "no_agreement_days" }, ref: "chip.s15.ref", plain: "chip.s15.plain" },
};

/** A section reference that opens a two-line plain explanation in a drawer. */
export function SectionChip({ id, config }: { id: ChipId; config: StatuteConfig | null }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const spec = CHIP_KEYS[id];
  const keys = Object.values(spec.vars);
  const vars: Record<string, string> = {};
  let missing = false;
  for (const [name, key] of Object.entries(spec.vars)) {
    const v = configText(config, key);
    if (v === null) missing = true;
    vars[name] = v ?? "…";
  }
  const entries = keys.map((k) => configEntry(config, k));
  const verified = entries.every((e) => e?.verified === true);
  const sourceRef = entries.map((e) => e?.source_ref).filter(Boolean).join(", ");

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("chip.open", { ref: t(spec.ref) })}
        className="mx-1 inline-flex items-center rounded-sm border border-ink-300 bg-ink-100 px-1.5 py-px align-baseline font-mono text-xs font-medium text-ink-800 hover:border-ink-600"
      >
        {t(spec.ref)}
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title={t(spec.ref)} width="sm">
        <div className="flex flex-col gap-4">
          <p className="text-lg leading-relaxed text-ink-900">{t(spec.plain, vars)}</p>
          {missing && <p className="text-sm text-warn">{t("chip.config_missing")}</p>}
          <div className="flex flex-wrap items-center gap-2 text-sm text-ink-600">
            <StatusIcon
              size="sm"
              tone={verified ? "ok" : "warn"}
              label={t(verified ? "badge.verified" : "badge.unverified")}
            />
            {sourceRef && <span>{t("chip.source", { ref: sourceRef })}</span>}
          </div>
        </div>
      </Drawer>
    </>
  );
}
