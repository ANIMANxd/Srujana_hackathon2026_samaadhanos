"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, BackendUnreachable, simulateSettlement } from "@/lib/api";
import { count, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import type { CaseRequest, SettlementSimulationResponse } from "@/lib/types";
import { Icon } from "../common/Icon";

/**
 * Illustrative terms (inputs, not legal values). The engine splits its own
 * claim for each; the browser only shows the figures it returns.
 */
const OPTIONS: { key: MessageKey; upfront: number; waiver: number; days: number }[] = [
  { key: "cfo.settle.full", upfront: 100, waiver: 0, days: 0 },
  { key: "cfo.settle.split", upfront: 50, waiver: 0, days: 30 },
  { key: "cfo.settle.split_waiver", upfront: 50, waiver: 25, days: 30 },
];

type State =
  | { kind: "loading" }
  | { kind: "ready"; results: SettlementSimulationResponse[] }
  | { kind: "offline" }
  | { kind: "error"; message: string };

export function CfoSettlementOptions({ caseId, request }: { caseId: string; request: CaseRequest }) {
  const { t } = useT();
  const href = useHref();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    Promise.all(
      OPTIONS.map((o) =>
        simulateSettlement(request, { upfront_pct: o.upfront.toFixed(2), waiver_pct: o.waiver.toFixed(2), days_to_second_payment: o.days }),
      ),
    )
      .then((results) => alive && setState({ kind: "ready", results }))
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof BackendUnreachable) setState({ kind: "offline" });
        else setState({ kind: "error", message: e instanceof ApiError ? e.message : t("state.error_title") });
      });
    return () => {
      alive = false;
    };
  }, [request, t]);

  return (
    <section aria-labelledby="cfo-settle" className="panel flex flex-col gap-4 p-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <div className="flex flex-col gap-1">
          <h3 id="cfo-settle" className="section-title">{t("cfo.settle.title")}</h3>
          <p className="text-sm text-ink-600">{t("cfo.settle.intro")}</p>
        </div>
        <Link href={href(`/case/${caseId}`, { send: 3 })} scroll={false} className="btn btn-secondary shrink-0 self-start">
          {t("cfo.settle.term_sheet")}
          <Icon name="arrow-right" className="h-4 w-4" />
        </Link>
      </div>

      {state.kind === "offline" && <p className="text-sm text-warn">{t("cfo.settle.offline")}</p>}
      {state.kind === "error" && <p className="text-sm text-block">{state.message}</p>}

      <ul className="grid gap-3 md:grid-cols-3">
        {OPTIONS.map((o, i) => {
          const r = state.kind === "ready" ? state.results[i] : null;
          const now = r?.payments.find((p) => p.kind === "UPFRONT");
          const later = r?.payments.find((p) => p.kind === "SECOND");
          return (
            <li key={o.key} className="flex flex-col gap-3 rounded-lg border border-rule p-4">
              <div className="flex flex-col gap-0.5">
                <span className="text-sm font-medium text-ink-950">{t(o.key)}</span>
                <span className="text-xs text-ink-500">{o.upfront === 100 ? t("cfo.settle.terms_full") : t("cfo.settle.terms", { upfront: o.upfront, days: count(o.days), waiver: o.waiver })}</span>
              </div>
              {r ? (
                <dl className="flex flex-col gap-1.5 text-sm">
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-ink-600">{t("cfo.settle.payable")}</dt>
                    <dd className="num font-semibold text-ink-950">{money(r.total_payable)}</dd>
                  </div>
                  {now && (
                    <div className="flex items-baseline justify-between gap-3">
                      <dt className="text-ink-600">{t("cfo.settle.now")}</dt>
                      <dd className="num text-ink-900">{money(now.amount)}</dd>
                    </div>
                  )}
                  {later && o.upfront < 100 && (
                    <div className="flex items-baseline justify-between gap-3">
                      <dt className="text-ink-600">{t("cfo.settle.later", { n: count(later.days_from_now) })}</dt>
                      <dd className="num text-ink-900">{money(later.amount)}</dd>
                    </div>
                  )}
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-ink-600">{t("cfo.settle.waived")}</dt>
                    <dd className="num text-ink-900">{money(r.interest_waived)}</dd>
                  </div>
                </dl>
              ) : (
                state.kind === "loading" && <div className="h-20 animate-pulse rounded-md bg-paper-sunk" aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
