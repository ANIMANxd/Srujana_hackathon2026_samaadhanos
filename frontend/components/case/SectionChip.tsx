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

/**
 * A statute tag, e.g. "MSMED s.16". The label may carry what the ENGINE decided
 * on this case ("deemed acceptance"); the drawer gives the plain rule, its
 * numbers from the statute config, and whether the source is verified.
 */
export function SectionChip({
  id,
  config,
  label,
}: {
  id: ChipId;
  config: StatuteConfig | null;
  /** Engine-derived label; defaults to the bare section reference. */
  label?: string;
}) {
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
      <button type="button" onClick={() => setOpen(true)} aria-label={t("chip.open", { ref: t(spec.ref) })} className="tag">
        <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${verified ? "bg-ok" : "bg-ink-300"}`} />
        {label ?? t(spec.ref)}
      </button>
      <Drawer open={open} onClose={() => setOpen(false)} title={t(spec.ref)} width="sm">
        <div className="flex flex-col gap-5">
          <p className="text-[1.0625rem] leading-relaxed text-ink-900">{t(spec.plain, vars)}</p>
          {label && <p className="text-sm text-ink-600">{t("chip.engine_note", { detail: label })}</p>}
          {missing && <p className="text-sm text-warn">{t("chip.config_missing")}</p>}
          <div className="flex flex-col items-start gap-2 border-t border-rule pt-4 text-sm text-ink-600">
            <StatusIcon size="sm" tone={verified ? "ok" : "warn"} label={t(verified ? "badge.verified" : "badge.unverified")} />
            {sourceRef && <span className="num text-xs">{t("chip.source", { ref: sourceRef })}</span>}
          </div>
        </div>
      </Drawer>
    </>
  );
}
