"use client";

import { useT } from "@/lib/i18n";
import type { Defense, DefenseStatus } from "@/lib/types";
import type { Tone } from "@/lib/derive";
import { Drawer } from "../common/Drawer";
import { StatusIcon } from "../common/StatusIcon";

export const DEFENSE_TONE: Record<DefenseStatus, Tone> = { STRONG: "ok", AT_RISK: "warn", OPEN_QUESTION: "info" };

/** Every argument the engine expects, with the evidence that answers it. */
export function DefensesDrawer({ defenses, open, onClose }: { defenses: Defense[]; open: boolean; onClose: () => void }) {
  const { t, tCode } = useT();
  return (
    <Drawer open={open} onClose={onClose} title={t("defense.drawer_title")} width="md">
      <p className="text-sm text-ink-600">{t("defense.drawer_intro")}</p>
      <ul className="mt-5 flex flex-col divide-y divide-rule border-y border-rule">
        {defenses.map((d) => (
          <li key={d.id} className="flex flex-col gap-2.5 py-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-[0.9375rem] leading-snug text-ink-950">“{d.buyer_says}”</p>
              <StatusIcon size="sm" tone={DEFENSE_TONE[d.status]} label={t(`defense.${d.status}`)} />
            </div>
            {d.status === "OPEN_QUESTION" ? (
              <p className="text-sm text-ink-600">{t("defense.open_note")}</p>
            ) : (
              <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[6rem_1fr]">
                {d.evidence_have.length > 0 && (
                  <>
                    <dt className="text-ink-500">{t("defense.have")}</dt>
                    <dd className="text-ink-800">{d.evidence_have.map((k) => tCode("evidence", k, k)).join(", ")}</dd>
                  </>
                )}
                {d.evidence_missing.length > 0 && (
                  <>
                    <dt className="text-ink-500">{t("defense.missing")}</dt>
                    <dd className="text-warn">{d.evidence_missing.map((k) => tCode("evidence", k, k)).join(", ")}</dd>
                  </>
                )}
              </dl>
            )}
            <span className="num text-xs text-ink-500">{d.rule_ref}</span>
          </li>
        ))}
      </ul>
    </Drawer>
  );
}
