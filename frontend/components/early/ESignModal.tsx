"use client";

import { useState } from "react";
import { ApiError, submitEsignOtp } from "@/lib/api";
import { money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Bid, ESignSession } from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { IdempotentButton } from "../common/IdempotentButton";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";
import { DemoBadge } from "../options/DemoBadge";

const OTP = /^\d{4,8}$/;

/**
 * The simulated eSign step. It states plainly that this is a demo and that no
 * Aadhaar number is collected: there is no such field. The code goes to the
 * server and nothing is decided here; signing completes when the server's track
 * moves on.
 */
export function ESignModal({
  open,
  onClose,
  caseId,
  invoiceNo,
  acceptedAmount,
  bid,
  session,
  version,
  offline,
  onConflict,
}: {
  open: boolean;
  onClose: () => void;
  caseId: string;
  invoiceNo: string;
  acceptedAmount: string;
  /** The selected bid, if the list still carries it. */
  bid: Bid | null;
  session: ESignSession | null;
  version: number | null;
  offline: boolean;
  onConflict: () => Promise<void> | void;
}) {
  const { t } = useT();
  const [otp, setOtp] = useState("");
  const [rejected, setRejected] = useState(false);
  const [result, setResult] = useState<ESignSession | null>(null);
  const shown = result ?? session;
  const signed = shown?.status === "SIGNED";

  return (
    <Drawer open={open} onClose={onClose} title={t("early.esign.title")} width="sm">
      <div className="flex flex-col gap-5">
        <Banner tone="warn" icon="info" message="early.esign.banner" />
        <p className="text-xs text-ink-500">{t("early.esign.template")}</p>

        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-ink-500">{t("early.esign.invoice")}</dt>
          <dd className="font-mono">{invoiceNo}</dd>
          <dt className="text-ink-500">{t("early.esign.amount")}</dt>
          <dd className="font-mono">{money(acceptedAmount)}</dd>
          {bid && (
            <>
              <dt className="text-ink-500">{bid.financier_alias}</dt>
              <dd className="font-mono">{money(bid.net_amount)}</dd>
            </>
          )}
          {shown && (
            <>
              <dt className="text-ink-500">{t("early.esign.session")}</dt>
              <dd className="font-mono">{shown.session_id}</dd>
            </>
          )}
        </dl>

        {!shown ? (
          <p role="alert" className="text-sm text-ink-700">
            {t("early.esign.no_session")}
          </p>
        ) : signed ? (
          <div className="flex flex-col gap-2" role="status">
            <StatusIcon tone="ok" label={t("early.esign.signed")} />
            {shown.signed_doc_sha256 && (
              <p className="break-all font-mono text-xs text-ink-600">
                {t("early.esign.hash")}: {shown.signed_doc_sha256}
              </p>
            )}
            <p className="text-sm text-ink-600">{t("early.sign.waiting")}</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <label>
              <span className="field-label">{t("early.esign.otp")}</span>
              <input
                className="field-input num max-w-[10rem]"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={otp}
                data-autofocus
                aria-invalid={rejected}
                aria-describedby="otp-hint"
                onChange={(e) => {
                  setOtp(e.target.value.replace(/\D/g, ""));
                  setRejected(false);
                }}
              />
              <span id="otp-hint" className="mt-1.5 block text-xs text-ink-500">
                {t("early.esign.otp_hint")}
              </span>
            </label>
            {rejected && (
              <p role="alert" className="text-sm text-block">
                {t("early.esign.bad_otp")}
              </p>
            )}
            <div>
              <IdempotentButton
                actionId={`esign.otp:${caseId}:${shown.session_id}:${otp}`}
                run={async (opts) => {
                  try {
                    setResult(await submitEsignOtp(caseId, otp, opts));
                  } catch (e) {
                    // A refused code is a definite answer, not a failure of the button.
                    if (e instanceof ApiError && e.status !== 409 && e.status < 500) {
                      setRejected(true);
                      return;
                    }
                    throw e;
                  }
                }}
                version={version}
                onConflict={onConflict}
                offline={offline}
                disabled={!OTP.test(otp)}
              >
                {t("early.esign.submit")}
              </IdempotentButton>
            </div>
          </div>
        )}
        <div>
          <DemoBadge />
        </div>
      </div>
    </Drawer>
  );
}
