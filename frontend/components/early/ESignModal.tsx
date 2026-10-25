"use client";

import { useState } from "react";
import { ApiError, esignTemplateUrl } from "@/lib/api";
import { useEarlyActions } from "@/lib/earlyActions";
import { money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Bid, ESignSession } from "@/lib/types";
import { timeLeft, useNow } from "@/lib/useNow";
import { Drawer } from "../common/Drawer";
import { Icon } from "../common/Icon";
import { IdempotentButton } from "../common/IdempotentButton";
import { Banner } from "../shell/Banners";
import { DemoBadge } from "../options/DemoBadge";

const OTP_LENGTH = 6;
const OTP = new RegExp(`^[0-9]{${OTP_LENGTH}}$`);
/** A whole number the server reported (`attempts_left`), or null: the count is never worked out here. */
function serverCount(v: unknown): number | null {
  return typeof v === "number" && Number.isInteger(v) && v >= 0 ? v : null;
}

/**
 * The simulated eSign step, shown as a modal-style panel (Esc closes, focus
 * stays inside, focus returns to the opener). It says plainly that it is a demo
 * and that no Aadhaar number is collected: there is no such field. The code goes
 * to the API, which forwards it to the mock provider. On success the panel
 * closes and the stepper waits for the server's track to move; nothing here
 * decides that signing worked.
 */
export function ESignModal({
  open,
  onClose,
  onSigned,
  caseId,
  invoiceNo,
  acceptedAmount,
  supplierName,
  buyerName,
  bid,
  session,
  version,
  offline,
  onConflict,
}: {
  open: boolean;
  onClose: () => void;
  /** The code was accepted; the caller closes this and waits for the server. */
  onSigned: () => void;
  caseId: string;
  invoiceNo: string;
  acceptedAmount: string;
  supplierName: string;
  buyerName: string;
  /** The selected bid, if the list still carries it. */
  bid: Bid | null;
  session: ESignSession | null;
  version: number | null;
  offline: boolean;
  onConflict: () => Promise<void> | void;
}) {
  const { t } = useT();
  const act = useEarlyActions();
  const [otp, setOtp] = useState("");
  const [wrong, setWrong] = useState(0);
  const [reported, setReported] = useState<number | null>(null);
  const now = useNow(1000);
  const left = session ? timeLeft(session.expires_at, now, true) : null;
  const expired = session?.status === "EXPIRED" || left?.expired === true;
  // From the refused-code answer, else from the session if the server includes it; never counted here.
  const attempts = reported ?? serverCount((session as { attempts_left?: unknown } | null)?.attempts_left);
  const failed = session?.status === "FAILED" || attempts === 0;
  const blocked = !session || expired || failed;
  const rejected = wrong > 0 && otp === "";
  const complete = OTP.test(otp);

  return (
    <Drawer open={open} onClose={onClose} title={t("early.esign.title")} width="sm">
      <div className="flex flex-col gap-5">
        <div className="rounded-lg border-2 border-dashed border-warn/60">
          <Banner tone="warn" icon="warn" message="early.esign.banner" />
        </div>
        <p className="text-xs text-ink-500">{t("early.esign.template")}</p>

        <section aria-label={t("early.esign.parties")} className="flex flex-col gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-ink-500">{t("early.esign.parties")}</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-ink-500">{t("early.esign.supplier")}</dt>
            <dd>{supplierName}</dd>
            <dt className="text-ink-500">{t("early.esign.buyer")}</dt>
            <dd>{buyerName}</dd>
            {bid && (
              <>
                <dt className="text-ink-500">{t("early.esign.financier")}</dt>
                <dd>
                  {bid.financier_alias} <span className="font-mono text-xs text-ink-500">{bid.id}</span>
                </dd>
              </>
            )}
            <dt className="text-ink-500">{t("early.esign.invoice")}</dt>
            <dd className="font-mono">{invoiceNo}</dd>
            <dt className="text-ink-500">{t("early.esign.amount")}</dt>
            <dd className="font-mono">{money(acceptedAmount)}</dd>
            {bid && (
              <>
                <dt className="font-medium text-ink-800">{t("early.esign.receive")}</dt>
                <dd className="font-mono font-semibold text-ink-950">{money(bid.net_amount)}</dd>
              </>
            )}
            {session && (
              <>
                <dt className="text-ink-500">{t("early.esign.session")}</dt>
                <dd className="font-mono">{session.session_id}</dd>
              </>
            )}
          </dl>
          <a href={esignTemplateUrl(caseId)} target="_blank" rel="noreferrer noopener" className="link inline-flex items-center gap-1 text-sm">
            <Icon name="doc" className="h-4 w-4" />
            {t("early.esign.template_link")}
          </a>
        </section>

        {session && !expired && left && (
          <p className="text-sm text-ink-700">
            <Icon name="clock" className="mr-1.5 inline h-4 w-4 align-text-bottom" />
            {t("early.esign.expires", { time: left.text })}
          </p>
        )}

        {!session ? (
          <p role="alert" className="text-sm text-ink-700">
            {t("early.esign.no_session")}
          </p>
        ) : expired ? (
          <p role="alert" className="text-sm text-ink-700">
            {t("early.esign.expired")}
          </p>
        ) : failed ? (
          <p role="alert" className="text-sm text-ink-700">
            {t("early.esign.out_of_attempts")}
          </p>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
            }}
          >
            <label>
              <span className="field-label">{t("early.esign.otp")}</span>
              <input
                className="field-input num max-w-[10rem] tracking-[0.3em]"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={OTP_LENGTH}
                value={otp}
                data-autofocus
                aria-invalid={rejected}
                aria-describedby="otp-hint otp-attempts"
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, OTP_LENGTH))}
              />
              <span id="otp-hint" className="mt-1.5 block text-xs text-ink-500">
                {t("early.esign.otp_hint", { n: OTP_LENGTH })}
              </span>
            </label>
            <p id="otp-attempts" className="text-xs text-ink-600">
              {attempts === null ? t("early.esign.attempts_limited") : attempts === 1 ? t("early.esign.attempts_one") : t("early.esign.attempts", { n: attempts })}
            </p>
            {/* Announced when it appears; cleared as soon as the person types again. */}
            <p role="alert" className="flex min-h-5 items-center gap-1.5 text-sm text-block">
              {rejected && (
                <>
                  <Icon name="warn" className="h-4 w-4 shrink-0" />
                  {t("early.esign.bad_otp")}
                </>
              )}
            </p>
            <div>
              <IdempotentButton
                actionId={`esign.otp:${caseId}:${session.session_id}:${otp}:${wrong}`}
                run={async (opts) => {
                  try {
                    await act.submitOtp(caseId, otp, opts);
                  } catch (e) {
                    // A refused code is a definite answer, not a failure of the button.
                    if (e instanceof ApiError && e.status !== 409 && e.status < 500) {
                      setWrong((n) => n + 1);
                      setReported(serverCount(e.details?.attempts_left));
                      setOtp("");
                      return;
                    }
                    throw e;
                  }
                  setOtp("");
                  onSigned();
                }}
                version={version}
                onConflict={onConflict}
                offline={offline}
                disabled={!complete || blocked}
              >
                {t("early.esign.submit")}
              </IdempotentButton>
            </div>
          </form>
        )}
        <div>
          <DemoBadge />
        </div>
      </div>
    </Drawer>
  );
}
