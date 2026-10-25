"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ApiError, BackendUnreachable, simulateSettlement } from "@/lib/api";
import { count, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseRequest, SettlementSimulationResponse } from "@/lib/types";

// Slider positions are the owner's terms (inputs), not legal values. They are
// sent as strings; the engine does every split.
const PCT_STEPS = { min: 0, max: 100, step: 5 };
const DAY_STEPS = { min: 0, max: 180, step: 15 };
const DEBOUNCE_MS = 300;

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: SettlementSimulationResponse }
  | { kind: "offline" }
  | { kind: "error"; message: string };

function Slider({
  label,
  value,
  display,
  range,
  onChange,
}: {
  label: string;
  value: number;
  display: string;
  range: { min: number; max: number; step: number };
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink-700">{label}</span>
        <span className="num font-medium text-ink-950">{display}</span>
      </span>
      <input
        type="range"
        className="w-full accent-ink-950"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function Line({ label, value, op, strong = false }: { label: string; value: string; op?: string; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-4 py-2 ${strong ? "border-t border-ink-950/20 pt-3" : ""}`}>
      <span className={`text-sm ${strong ? "font-medium text-ink-950" : "text-ink-600"}`}>
        {op && <span className="mr-2 text-xs text-ink-500">{op}</span>}
        {label}
      </span>
      <span className={`num ${strong ? "text-base font-semibold text-ink-950" : "text-sm text-ink-900"}`}>{money(value)}</span>
    </div>
  );
}

function Box({ children }: { children: ReactNode }) {
  return <div className="flex flex-col rounded-lg border border-rule px-4 py-3">{children}</div>;
}

/**
 * Settlement simulator (stretch): the owner picks terms, POST /simulate-settlement
 * returns the split of the engine's own claim, and this lays it out line by line.
 * "minus" and "equals" only label the engine's figures; nothing is added here.
 */
export function SettlementSimulator({ request, hasClaim }: { request: CaseRequest; hasClaim: boolean }) {
  const { t } = useT();
  const [upfront, setUpfront] = useState(50);
  const [waiver, setWaiver] = useState(0);
  const [days, setDays] = useState(30);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!hasClaim) return;
    let alive = true;
    const timer = setTimeout(() => {
      simulateSettlement(request, { upfront_pct: upfront.toFixed(2), waiver_pct: waiver.toFixed(2), days_to_second_payment: days })
        .then((data) => alive && setState({ kind: "ready", data }))
        .catch((e: unknown) => {
          if (!alive) return;
          if (e instanceof BackendUnreachable) setState({ kind: "offline" });
          else setState({ kind: "error", message: e instanceof ApiError ? e.message : t("state.error_title") });
        });
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [request, upfront, waiver, days, hasClaim, t]);

  const d = state.kind === "ready" ? state.data : null;
  const upfrontPay = d?.payments.find((p) => p.kind === "UPFRONT");
  const secondPay = d?.payments.find((p) => p.kind === "SECOND");

  return (
    <section aria-labelledby="settle-title" className="panel flex flex-col gap-5 p-6">
      <div className="flex flex-col gap-1">
        <h2 id="settle-title" className="section-title">{t("settle.title")}</h2>
        <p className="text-sm text-ink-600">{t("settle.intro")}</p>
      </div>

      {!hasClaim ? (
        <p className="text-sm text-ink-600">{t("settle.no_claim")}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <div className="flex flex-col gap-5">
            <Slider label={t("settle.upfront")} value={upfront} display={t("settle.pct_value", { n: upfront })} range={PCT_STEPS} onChange={setUpfront} />
            <Slider label={t("settle.waiver")} value={waiver} display={t("settle.pct_value", { n: waiver })} range={PCT_STEPS} onChange={setWaiver} />
            <Slider label={t("settle.days")} value={days} display={t("settle.days_value", { n: count(days) })} range={DAY_STEPS} onChange={setDays} />
          </div>

          <div aria-live="polite" className="flex flex-col gap-3">
            {state.kind === "offline" && <p className="text-sm text-warn">{t("settle.needs_backend")}</p>}
            {state.kind === "error" && <p className="text-sm text-block">{state.message}</p>}
            {state.kind === "loading" && <p className="text-sm text-ink-500">{t("settle.loading")}</p>}
            {d && (
              <>
                <Box>
                  <Line label={t("settle.total_claim")} value={d.total_claim} />
                  <Line label={t("settle.waived")} value={d.interest_waived} op={t("settle.minus")} />
                  <Line label={t("settle.payable")} value={d.total_payable} op={t("settle.equals")} strong />
                </Box>
                <div className="grid gap-3 sm:grid-cols-2">
                  {upfrontPay && (
                    <Box>
                      <span className="text-xs text-ink-500">{t("settle.upfront_payment")}</span>
                      <span className="num mt-1 text-lg font-semibold text-ink-950">{money(upfrontPay.amount)}</span>
                    </Box>
                  )}
                  {secondPay && (
                    <Box>
                      <span className="text-xs text-ink-500">
                        {t("settle.second_payment")} · {t("settle.due_in", { n: count(secondPay.days_from_now) })}
                      </span>
                      <span className="num mt-1 text-lg font-semibold text-ink-950">{money(secondPay.amount)}</span>
                    </Box>
                  )}
                </div>
                <Box>
                  <Line label={t("settle.principal_paid")} value={d.principal_paid} />
                  <Line label={t("settle.interest_paid")} value={d.interest_paid} />
                  <Line label={t("settle.net")} value={d.net_recovery} strong />
                </Box>
                {d.assumptions.length > 0 && (
                  <details className="text-xs text-ink-600">
                    <summary className="cursor-pointer font-medium text-ink-700 hover:text-ink-950">{t("settle.assumptions")}</summary>
                    <ul className="mt-2 flex list-disc flex-col gap-1 pl-4">
                      {d.assumptions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
