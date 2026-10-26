"use client";

// "Record payment": a small form in a drawer. It reads the case fresh when it
// opens, prefills the amount with the engine's current total (as sent, no sums
// here) and the date with the server's calendar date, and posts to
// POST /cases/{id}/payments. The server checks the cap; its plain-English
// message is shown as sent. A financed invoice answers 409, and that message
// replaces the form. Afterwards the caller re-reads the case.

import { useEffect, useId, useRef, useState } from "react";
import { ApiError, BackendUnreachable, getCase, recordPayment, type PaymentInput } from "@/lib/api";
import { bookAction } from "@/lib/customerBook";
import { idempotencyKeyFor, releaseIdempotencyKey } from "@/lib/idempotency";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import type { PaymentMethod } from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { Skeleton } from "../common/States";
import { AMOUNT, DATE, isRealDate } from "../common/TextField";

const METHODS: PaymentMethod[] = ["bank", "upi", "cheque", "cash", "other"];

type Start = { amount: string; paidOn: string; offline: boolean };

function Form({ caseId, start, onRecorded, onClose }: { caseId: string; start: Start; onRecorded: () => void | Promise<void>; onClose: () => void }) {
  const { t } = useT();
  const ids = { amount: useId(), date: useId(), method: useId(), note: useId(), err: useId() };
  const [amount, setAmount] = useState(start.amount);
  const [paidOn, setPaidOn] = useState(start.paidOn);
  const [method, setMethod] = useState<PaymentMethod>("bank");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [financed, setFinanced] = useState<string | null>(null);
  const busy = useRef(false);

  const amountOk = AMOUNT.test(amount) && Number(amount) > 0;
  const dateOk = DATE.test(paidOn) && isRealDate(paidOn);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (busy.current || start.offline || !amountOk || !dateOk) return;
    busy.current = true;
    setPending(true);
    setFailure(null);
    const input: PaymentInput = { amount, paid_on: paidOn, method, note: note.trim() === "" ? null : note.trim() };
    const actionId = bookAction.recordPayment(caseId, input);
    try {
      await recordPayment(caseId, input, { idempotencyKey: idempotencyKeyFor(actionId) });
      releaseIdempotencyKey(actionId);
      await onRecorded();
      onClose();
    } catch (err) {
      if (err instanceof BackendUnreachable) {
        // Same payload, same key: a retry replays if the first try did land.
        setFailure(t("pay.unreachable"));
      } else {
        releaseIdempotencyKey(actionId);
        if (err instanceof ApiError && err.status === 409) setFinanced(err.message);
        else setFailure(err instanceof ApiError ? err.message : t("pay.failed"));
      }
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  if (financed) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="rounded-lg border border-warn/30 bg-warn-wash p-4 text-sm text-ink-900">
          {financed}
        </p>
        <button type="button" className="btn btn-secondary self-start" data-autofocus onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <p className="text-sm text-ink-600">{t("pay.hint")}</p>
      <label className="block" htmlFor={ids.amount}>
        <span className="field-label">{t("pay.amount")}</span>
        <input
          id={ids.amount}
          data-autofocus
          inputMode="decimal"
          className="field-input num"
          value={amount}
          onChange={(e) => setAmount(e.target.value.trim())}
          aria-invalid={touched && !amountOk}
          aria-describedby={ids.err}
        />
      </label>
      <label className="block" htmlFor={ids.date}>
        <span className="field-label">{t("pay.date")}</span>
        <input
          id={ids.date}
          className="field-input num"
          value={paidOn}
          placeholder={t("common.date_format")}
          onChange={(e) => setPaidOn(e.target.value.trim())}
          aria-invalid={touched && !dateOk}
          aria-describedby={ids.err}
        />
      </label>
      <label className="block" htmlFor={ids.method}>
        <span className="field-label">{t("pay.method")}</span>
        <select id={ids.method} className="field-input" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
          {METHODS.map((m) => (
            <option key={m} value={m}>
              {t(`pay.method.${m}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      <label className="block" htmlFor={ids.note}>
        <span className="field-label">{t("pay.note")}</span>
        <input id={ids.note} className="field-input" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
      </label>

      <div id={ids.err} role="alert" className="text-sm text-block">
        {touched && !amountOk && <p>{t("pay.invalid_amount")}</p>}
        {touched && !dateOk && <p>{t("pay.invalid_date")}</p>}
        {failure && <p>{failure}</p>}
      </div>
      {start.offline && <p className="text-sm text-ink-600">{t("pay.offline")}</p>}

      <div className="flex flex-wrap gap-2">
        <button type="submit" className="btn btn-primary" disabled={pending || start.offline} aria-busy={pending}>
          {t("pay.save")}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          {t("pay.cancel")}
        </button>
      </div>
    </form>
  );
}

export function RecordPaymentDrawer({
  caseId,
  open,
  onClose,
  onRecorded,
}: {
  caseId: string;
  open: boolean;
  onClose: () => void;
  /** Re-read the case (and anything built from it) after the payment landed. */
  onRecorded: () => void | Promise<void>;
}) {
  const { t } = useT();
  const [start, setStart] = useState<Start | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    getCase(caseId).then(
      (r) => {
        if (!alive) return;
        const ev = r.data.latest_evaluation;
        setStart({
          amount: ev?.financials?.total_claim ?? "",
          paidOn: ev?.calculation_date ?? "",
          offline: r.source !== "live",
        });
      },
      () => {
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
      setStart(null);
      setFailed(false);
    };
  }, [open, caseId]);

  return (
    <Drawer open={open} onClose={onClose} title={t("pay.form_title")} width="sm">
      {failed ? (
        <p role="alert" className="text-sm text-ink-700">
          {t("pay.load_failed")}
        </p>
      ) : start ? (
        <Form caseId={caseId} start={start} onRecorded={onRecorded} onClose={onClose} />
      ) : (
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">{t("state.loading")}</span>
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      )}
    </Drawer>
  );
}
