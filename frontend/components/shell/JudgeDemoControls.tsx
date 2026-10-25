"use client";

import { useEffect, useState } from "react";
import { ApiError, getDeliveries, setMockClock, setMockScenario, verifyEvents, type Source } from "@/lib/api";
import { announceCaseChange } from "@/lib/useCases";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import type { ChainVerifyResult, WebhookDelivery } from "@/lib/types";
import { IdempotentButton } from "../common/IdempotentButton";
import { StatusIcon } from "../common/StatusIcon";

/** The mock providers' scenarios (architecture_v4 section 7.4). */
const SCENARIOS = [
  "happy_path",
  "buyer_rejects",
  "buyer_window_expires",
  "no_bids",
  "bids_expire",
  "esign_wrong_otp",
  "esign_expires",
  "webhook_duplicate",
  "webhook_out_of_order",
  "webhook_bad_signature",
  "webhook_delayed",
  "payout_failed_then_succeeds",
  "buyer_defaults_after_disbursal",
] as const;

const POLL_MS = 3000;
const SHOWN = 30;

function DeliveryBadge({ d }: { d: WebhookDelivery }) {
  const { t } = useT();
  switch (d.outcome) {
    case "APPLIED":
      return <StatusIcon size="sm" tone="ok" label={t("judge.demo.d.applied")} />;
    case "DUPLICATE":
      return <StatusIcon size="sm" tone="info" icon="copy" label={t("judge.demo.d.duplicate")} />;
    case "PARKED":
      return <StatusIcon size="sm" tone="warn" icon="clock" label={t("judge.demo.d.parked")} />;
    default:
      return <StatusIcon size="sm" tone="block" label={t("judge.demo.d.rejected")} />;
  }
}

/** A live log of the webhook inbox. Polled while the console is open. */
function DeliveryLog({ open }: { open: boolean }) {
  const { t } = useT();
  const [rows, setRows] = useState<WebhookDelivery[] | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    const load = () =>
      getDeliveries().then(
        (r) => {
          if (!alive) return;
          setRows(r.data);
          setSource(r.source);
          setFailed(false);
        },
        () => alive && setFailed(true),
      );
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [open]);

  return (
    <div className="flex flex-col gap-2" aria-live="polite">
      {source === "offline" && <p className="text-xs text-warn">{t("judge.demo.d.sample")}</p>}
      {failed && !rows && <p className="text-sm text-ink-600">{t("judge.demo.d.unavailable")}</p>}
      {rows && rows.length === 0 && <p className="text-sm text-ink-500">{t("judge.demo.d.empty")}</p>}
      {rows && rows.length > 0 && (
        <ul className="flex flex-col divide-y divide-rule rounded-lg border border-rule text-sm">
          {rows.slice(0, SHOWN).map((d) => (
            <li key={`${d.provider}-${d.provider_event_id}-${d.received_at}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <span className="flex min-w-0 flex-col">
                <span className="font-mono text-xs text-ink-900">{d.provider_event_id}</span>
                <span className="text-xs text-ink-500">
                  {d.provider} · {d.received_at.slice(11, 19)} UTC
                  {!d.signature_ok && ` · ${t("judge.demo.d.bad_signature")}`}
                </span>
              </span>
              <DeliveryBadge d={d} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Demo controls for a stored case: mock scenario, clock, audit-chain check,
 * reset, and the webhook delivery log. Judge console only; the console itself
 * is absent when /health reports production.
 */
export function JudgeDemoControls({ caseId, open }: { caseId: string | null; open: boolean }) {
  const { t } = useT();
  const [scenario, setScenario] = useState<string>(SCENARIOS[0]);
  const [days, setDays] = useState("7");
  const [note, setNote] = useState<string | null>(null);
  const [chain, setChain] = useState<{ result: ChainVerifyResult; source: Source } | null>(null);
  const [chainError, setChainError] = useState<string | null>(null);
  const daysOk = /^\d{1,3}$/.test(days) && Number(days) > 0;

  const failMessage = (e: unknown) => (e instanceof ApiError ? e.message : t("action.failed"));

  return (
    <div className="flex flex-col gap-6">
      {!caseId && <p className="text-sm text-ink-500">{t("judge.demo.no_case")}</p>}

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-ink-950">{t("judge.demo.scenario")}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[14rem] flex-1">
            <span className="field-label">{t("judge.demo.scenario_label")}</span>
            <select className="field-input" value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {SCENARIOS.map((s) => (
                <option key={s} value={s}>
                  {t(`judge.demo.s.${s}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <IdempotentButton
            actionId={`mock.scenario:${caseId}:${scenario}`}
            run={async (opts) => {
              if (!caseId) return;
              try {
                await setMockScenario({ case_id: caseId, scenario }, opts);
                setNote(t("judge.demo.scenario_set", { name: scenario }));
              } catch (e) {
                if (e instanceof ApiError && e.status !== 409) setNote(failMessage(e));
                else throw e;
              }
            }}
            onConflict={() => undefined}
            disabled={!caseId}
            className="btn btn-secondary"
          >
            {t("judge.demo.apply")}
          </IdempotentButton>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-ink-950">{t("judge.demo.clock")}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <label>
            <span className="field-label">{t("judge.demo.days")}</span>
            <input
              className="field-input num w-24"
              inputMode="numeric"
              value={days}
              aria-invalid={!daysOk}
              onChange={(e) => setDays(e.target.value.replace(/\D/g, "").slice(0, 3))}
            />
          </label>
          <IdempotentButton
            actionId={`mock.clock.advance:${days}`}
            run={async (opts) => {
              try {
                await setMockClock({ advance_days: Number(days) }, opts);
                setNote(t("judge.demo.clock_advanced", { n: days }));
                if (caseId) announceCaseChange(caseId);
              } catch (e) {
                if (e instanceof ApiError && e.status !== 409) setNote(failMessage(e));
                else throw e;
              }
            }}
            onConflict={() => undefined}
            disabled={!daysOk}
            className="btn btn-secondary"
          >
            {t("judge.demo.advance")}
          </IdempotentButton>
          <IdempotentButton
            actionId="mock.clock.reset"
            run={async (opts) => {
              try {
                await setMockClock({ reset: true }, opts);
                setNote(t("judge.demo.clock_reset_done"));
                if (caseId) announceCaseChange(caseId);
              } catch (e) {
                if (e instanceof ApiError && e.status !== 409) setNote(failMessage(e));
                else throw e;
              }
            }}
            onConflict={() => undefined}
            className="btn btn-quiet"
          >
            {t("judge.demo.reset_clock")}
          </IdempotentButton>
        </div>
      </div>

      {note && (
        <p role="status" className="text-sm text-ink-700">
          {note}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-ink-950">{t("judge.demo.chain")}</h4>
        <div className="flex flex-wrap items-center gap-3">
          <IdempotentButton
            actionId={`chain.verify:${caseId}`}
            run={async () => {
              if (!caseId) return;
              try {
                const r = await verifyEvents(caseId);
                setChain({ result: r.data, source: r.source });
                setChainError(null);
              } catch (e) {
                setChain(null);
                setChainError(failMessage(e));
              }
            }}
            onConflict={() => undefined}
            disabled={!caseId}
            className="btn btn-secondary"
          >
            {t("judge.demo.verify")}
          </IdempotentButton>
          <span role="status" aria-live="polite">
            {chain &&
              (chain.result.valid ? (
                <StatusIcon tone="ok" label={t("judge.demo.chain_ok", { n: chain.result.checked })} />
              ) : (
                <StatusIcon tone="block" label={t("judge.demo.chain_broken", { seq: chain.result.first_bad_seq ?? 0 })} />
              ))}
            {chainError && <span className="text-sm text-ink-700">{chainError}</span>}
          </span>
        </div>
        {chain?.source === "offline" && <p className="text-xs text-warn">{t("judge.demo.d.sample")}</p>}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-ink-950">{t("judge.demo.reset")}</h4>
        <p className="text-sm text-ink-700">{t("judge.demo.reset_steps")}</p>
        <code className="block rounded-md bg-paper-sunk px-3 py-2 font-mono text-xs text-ink-900">make db-reset</code>
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium text-ink-950">{t("judge.demo.deliveries")}</h4>
        <DeliveryLog open={open} />
      </div>
    </div>
  );
}
