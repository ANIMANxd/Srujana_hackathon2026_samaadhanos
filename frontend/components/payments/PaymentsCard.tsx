"use client";

// Payments under the money card: what the owner says was received, with the
// ones they voided kept and marked. "Record payment" opens the form; "Void" asks
// first. Every change re-reads the case, so the amounts on screen are the
// engine's, not anything worked out here.

import { useState } from "react";
import { ApiError, BackendUnreachable, voidPayment } from "@/lib/api";
import { announceBookChange, bookAction } from "@/lib/customerBook";
import { date, money } from "@/lib/format";
import { idempotencyKeyFor, releaseIdempotencyKey } from "@/lib/idempotency";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import type { Payment } from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { Money } from "../common/Money";
import { StatusIcon } from "../common/StatusIcon";
import { RecordPaymentDrawer } from "./RecordPaymentDrawer";

export function PaymentsCard({
  caseId,
  payments,
  offline,
  refresh,
}: {
  caseId: string;
  payments: Payment[] | null;
  offline: boolean;
  /** Re-read the case and the payment list. */
  refresh: () => void | Promise<void>;
}) {
  const { t } = useT();
  const [recording, setRecording] = useState(false);
  const [voiding, setVoiding] = useState<Payment | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changed = async () => {
    announceBookChange();
    await refresh();
  };

  async function confirmVoid() {
    if (!voiding || pending) return;
    const p = voiding;
    const actionId = bookAction.voidPayment(caseId, p.id);
    setPending(true);
    setError(null);
    try {
      await voidPayment(caseId, p.id, { idempotencyKey: idempotencyKeyFor(actionId) });
      releaseIdempotencyKey(actionId);
      await changed();
      setVoiding(null);
    } catch (e) {
      if (e instanceof BackendUnreachable) setError(t("pay.unreachable"));
      else {
        releaseIdempotencyKey(actionId);
        setError(e instanceof ApiError ? e.message : t("pay.failed"));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="payments-title" className="panel flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 id="payments-title" className="section-title">
          {t("pay.title")}
        </h2>
        <button type="button" className="btn btn-secondary min-h-8 px-3 text-xs" disabled={offline} onClick={() => setRecording(true)} aria-haspopup="dialog">
          {t("pay.record")}
        </button>
      </div>
      {offline && <p className="text-xs text-ink-500">{t("pay.offline")}</p>}

      {payments === null ? null : payments.length === 0 ? (
        <p className="text-sm text-ink-600">{t("pay.none")}</p>
      ) : (
        <ul className="divide-y divide-rule">
          {payments.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5">
              <div className={`flex min-w-0 flex-col ${p.voided_at ? "text-ink-500" : "text-ink-900"}`}>
                <span className="flex flex-wrap items-baseline gap-x-3">
                  <Money value={p.amount} className={`text-sm ${p.voided_at ? "line-through" : ""}`} />
                  <span className="text-xs">{date(p.paid_on)}</span>
                  <span className="text-xs">{t(`pay.method.${p.method}` as MessageKey)}</span>
                </span>
                {p.note && <span className="break-words text-xs">{p.note}</span>}
              </div>
              {p.voided_at ? (
                <StatusIcon size="sm" tone="info" icon="close" label={t("pay.voided")} />
              ) : (
                <button
                  type="button"
                  className="btn btn-quiet min-h-8 px-2 text-xs"
                  disabled={offline}
                  aria-haspopup="dialog"
                  onClick={() => {
                    setError(null);
                    setVoiding(p);
                  }}
                >
                  {t("pay.void")}
                  <span className="sr-only"> {t("pay.void_sr", { amount: money(p.amount), date: date(p.paid_on) })}</span>
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <RecordPaymentDrawer caseId={caseId} open={recording} onClose={() => setRecording(false)} onRecorded={changed} />

      <Drawer open={voiding !== null} onClose={() => setVoiding(null)} title={t("pay.void_title")} width="sm">
        {voiding && (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-ink-700">{t("pay.void_body", { amount: money(voiding.amount), date: date(voiding.paid_on) })}</p>
            {error && (
              <p role="alert" className="rounded-lg border border-warn/30 bg-warn-wash p-3 text-sm text-ink-900">
                {error}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-primary" data-autofocus onClick={confirmVoid} disabled={pending} aria-busy={pending}>
                {t("pay.void_confirm")}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setVoiding(null)}>
                {t("pay.void_keep")}
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </section>
  );
}
