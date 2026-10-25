"use client";

import { date as fmtDate, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { PayoutStatus } from "@/lib/types";
import { StatusIcon } from "../common/StatusIcon";

/** The simulated payout: MOCK reference, MOCK UTR and amount, exactly as the server reports them. */
export function SettlementStatus({ payout }: { payout: PayoutStatus | null }) {
  const { t } = useT();
  if (!payout) {
    return (
      <p role="status" className="text-sm text-ink-600">
        {t("early.money.pending")}
        <span className="mt-1 block text-xs text-ink-500">{t("early.money.pending_hint")}</span>
      </p>
    );
  }
  const received = payout.status === "PROCESSED";
  return (
    <div className="flex flex-col gap-3" role="status">
      {received ? (
        <StatusIcon tone="ok" label={t("early.money.received")} />
      ) : (
        <StatusIcon tone="info" icon="clock" label={t("early.money.pending")} />
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-ink-500">{t("early.money.ref")}</dt>
        <dd className="font-mono">{payout.payout_ref}</dd>
        <dt className="text-ink-500">{t("early.money.utr")}</dt>
        <dd className="font-mono">{payout.utr ?? "—"}</dd>
        <dt className="text-ink-500">{t("early.money.amount")}</dt>
        <dd className="font-mono font-semibold text-ink-950">{money(payout.amount)}</dd>
        {payout.settled_at && (
          <>
            <dt className="text-ink-500">{t("early.money.at")}</dt>
            <dd>{fmtDate(payout.settled_at.slice(0, 10))}</dd>
          </>
        )}
      </dl>
      <p className="text-xs text-ink-500">{t("early.money.simulated")}</p>
    </div>
  );
}
