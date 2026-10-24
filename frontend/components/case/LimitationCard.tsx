"use client";

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
  return (
    <section aria-labelledby="limitation-title" className="panel flex flex-col gap-3 p-5">
      <h2 id="limitation-title" className="ledger-rule font-display text-xl font-semibold text-ink-950">
        {t("limitation.title")}
      </h2>
      <div className="flex flex-wrap items-center gap-3">
        <StatusIcon tone={TONE[limitation.status]} icon="clock" label={t(`limitation.${limitation.status}`)} />
        {limitation.expiry && <span className="num text-ink-900">{t("limitation.expiry", { date: date(limitation.expiry) })}</span>}
      </div>
      {!limitation.expiry && <p className="text-sm text-ink-700">{t("limitation.unknown_body")}</p>}
      <p className="text-sm text-ink-700">{t("limitation.restart_hint")}</p>
      {limitation.events.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-ink-800">{t("limitation.events")}</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {limitation.events.map((e, i) => (
              <li key={`${e.date}-${i}`} className="flex flex-wrap items-center gap-2">
                <span className="num text-ink-800">{date(e.date)}</span>
                <span>{t(`ack.${e.kind}`)}</span>
                <StatusIcon
                  size="sm"
                  tone={e.restarts_clock ? "ok" : "info"}
                  label={t(e.restarts_clock ? "limitation.event_restarts" : "limitation.event_no_restart")}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
