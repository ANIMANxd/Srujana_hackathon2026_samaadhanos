"use client";

import { useState } from "react";
import type { Tone } from "@/lib/derive";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Limitation, LimitationStatus } from "@/lib/types";
import { StatusIcon } from "../common/StatusIcon";

const TONE: Record<LimitationStatus, Tone> = {
  OK: "ok",
  WARN_12M: "warn",
  WARN_6M: "warn",
  EXPIRED: "block",
  UNKNOWN: "info",
};

export function LimitationCard({ limitation }: { limitation: Limitation }) {
  const { t } = useT();
  const [why, setWhy] = useState(false);
  return (
    <section aria-labelledby="limitation-title" className="panel flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 id="limitation-title" className="section-title">{t("limitation.title")}</h2>
        <button type="button" className="link text-xs" aria-expanded={why} onClick={() => setWhy((v) => !v)}>
          {why ? t("common.hide") : t("common.why")}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <StatusIcon size="sm" tone={TONE[limitation.status]} icon="clock" label={t(`limitation.${limitation.status}`)} />
        {limitation.expiry && <span className="num text-sm text-ink-950">{t("limitation.expiry", { date: date(limitation.expiry) })}</span>}
      </div>
      {why && (
        <div className="flex flex-col gap-1.5 text-sm text-ink-600">
          {!limitation.expiry && <p>{t("limitation.unknown_body")}</p>}
          <p>{t("limitation.restart_hint")}</p>
        </div>
      )}
      {limitation.events.length > 0 && (
        <ul className="flex flex-col gap-2 border-t border-rule pt-3 text-sm">
          {limitation.events.map((e, i) => (
            <li key={`${e.date}-${i}`} className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <span className="num text-xs text-ink-500">{date(e.date)}</span>
                <span className="text-ink-900">{t(`ack.${e.kind}`)}</span>
              </span>
              <StatusIcon
                size="sm"
                tone={e.restarts_clock ? "ok" : "info"}
                label={t(e.restarts_clock ? "limitation.event_restarts" : "limitation.event_no_restart")}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
