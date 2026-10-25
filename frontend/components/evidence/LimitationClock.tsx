"use client";

import type { Tone } from "@/lib/derive";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Limitation, LimitationStatus } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { Meaning } from "./Meaning";

const BANDS: Exclude<LimitationStatus, "UNKNOWN">[] = ["OK", "WARN_12M", "WARN_6M", "EXPIRED"];
const TONE: Record<LimitationStatus, Tone> = { OK: "ok", WARN_12M: "warn", WARN_6M: "warn", EXPIRED: "block", UNKNOWN: "info" };
const FILL: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", block: "bg-block", info: "bg-info" };

/**
 * The limitation clock as the engine's warning bands (6.5). The band and the
 * end date are the engine's; the browser counts nothing, so with no end date
 * (UNKNOWN) the track stays empty and says so.
 */
export function LimitationClock({ limitation }: { limitation: Limitation }) {
  const { t } = useT();
  const current = limitation.status;
  return (
    <section aria-labelledby="clock-title" className="panel flex flex-col gap-5 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="clock-title" className="section-title">{t("clock.title")}</h2>
        <StatusIcon size="sm" tone={TONE[current]} icon="clock" label={t(`limitation.${current}`)} />
      </div>

      <p className="figure text-2xl text-ink-950">
        {limitation.expiry ? t("clock.ends", { date: date(limitation.expiry) }) : <span className="text-ink-500">{t("clock.no_date")}</span>}
      </p>

      <div className="flex flex-col gap-2">
        <p className="eyebrow">{t("clock.bands")}</p>
        <ol className="grid grid-cols-4 gap-1">
          {BANDS.map((b) => {
            const active = b === current;
            return (
              <li key={b} aria-current={active ? "step" : undefined} className="flex flex-col gap-1.5">
                <span className={`h-1.5 rounded-full ${active ? FILL[TONE[b]] : "bg-paper-sunk"}`} />
                <span className={`flex items-center gap-1 text-xs ${active ? "font-medium text-ink-950" : "text-ink-500"}`}>
                  {active && <Icon name="arrow-right" className="h-3 w-3" />}
                  {t(`clock.band.${b}`)}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      {limitation.events.length > 0 && (
        <ul className="flex flex-col gap-2 border-t border-rule pt-4 text-sm">
          {limitation.events.map((e, i) => (
            <li key={`${e.date}-${i}`} className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <span className="num text-xs text-ink-500">{date(e.date)}</span>
                <span className="text-ink-900">{t(`ack.${e.kind}`)}</span>
              </span>
              <StatusIcon size="sm" tone={e.restarts_clock ? "ok" : "info"} label={t(e.restarts_clock ? "limitation.event_restarts" : "limitation.event_no_restart")} />
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-1 rounded-lg border border-rule px-4 py-3">
        <p className="eyebrow">{t("clock.restart_title")}</p>
        <p className="text-sm text-ink-800">{t("limitation.restart_hint")}</p>
      </div>

      <Meaning block="limitation" code={current} />
    </section>
  );
}
