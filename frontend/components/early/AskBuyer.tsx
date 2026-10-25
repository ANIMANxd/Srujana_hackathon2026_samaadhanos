"use client";

import { useState } from "react";
import { useEarlyActions } from "@/lib/earlyActions";
import { useT } from "@/lib/i18n";
import { IdempotentButton } from "../common/IdempotentButton";
import { StatusIcon } from "../common/StatusIcon";
import { Icon } from "../common/Icon";
import { SendButtons, isPhoneValid } from "../send/SendButtons";

/**
 * Step 2. The owner edits a note and sends it themselves (WhatsApp, email or
 * copy); "Request acceptance" asks the platform (a mock) to ask the buyer. The
 * status line is whatever the server's track says; this component never
 * decides that the buyer accepted.
 */
export function AskBuyer({
  caseId,
  invoiceNo,
  canRequest,
  waiting,
  version,
  offline,
  onConflict,
}: {
  caseId: string;
  invoiceNo: string;
  /** The server offers request_buyer_acceptance. */
  canRequest: boolean;
  /** The server says AWAITING_BUYER_ACCEPTANCE. */
  waiting: boolean;
  version: number | null;
  offline: boolean;
  onConflict: () => Promise<void> | void;
}) {
  const { t } = useT();
  const act = useEarlyActions();
  const [edited, setEdited] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const text = edited ?? t("early.ask.message", { invoice: invoiceNo });
  const phoneValid = isPhoneValid(phone);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-700">{t("early.ask.intro")}</p>

      <label>
        <span className="field-label">{t("early.ask.message_label")}</span>
        <textarea className="field-input min-h-24 text-sm" value={text} onChange={(e) => setEdited(e.target.value)} />
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <label>
          <span className="field-label">{t("send.phone")}</span>
          <input
            className="field-input num"
            inputMode="numeric"
            value={phone}
            aria-invalid={!phoneValid}
            onChange={(e) => setPhone(e.target.value.replace(/\s/g, ""))}
          />
          <span className={`mt-1.5 block text-xs ${phoneValid ? "text-ink-500" : "text-block"}`}>
            {t(phoneValid ? "send.phone_hint" : "send.phone_invalid")}
          </span>
        </label>
        <label>
          <span className="field-label">{t("send.email")}</span>
          <input className="field-input" type="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} />
        </label>
      </div>

      <label className="flex items-start gap-3 rounded-lg border border-rule bg-paper px-4 py-3">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-ink-950" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
        <span className="text-sm font-medium text-ink-950">{t("send.reviewed")}</span>
      </label>

      <div className="flex flex-wrap items-start gap-2">
        <SendButtons
          text={text}
          subject={t("early.ask.subject", { invoice: invoiceNo })}
          phone={phone}
          email={email}
          enabled={reviewed && text.trim().length > 0}
        />
      </div>
      <p className="flex items-center gap-2 text-xs text-ink-500">
        <Icon name="lock" className="h-3.5 w-3.5" />
        {t("send.disclaimer")}
      </p>

      {canRequest && (
        <div>
          <IdempotentButton
            actionId={`financing.accept:${caseId}`}
            run={async (opts) => {
              await act.requestAcceptance(caseId, opts);
              await onConflict();
            }}
            version={version}
            onConflict={onConflict}
            offline={offline}
          >
            {t("early.ask.request")}
          </IdempotentButton>
        </div>
      )}

      {waiting && (
        <div role="status" aria-live="polite" className="flex flex-col gap-1">
          <StatusIcon tone="info" icon="clock" label={t("early.ask.waiting")} />
          <span className="text-xs text-ink-500">{t("early.ask.waiting_hint")}</span>
        </div>
      )}
    </div>
  );
}
