"use client";

import type { MutationOptions } from "@/lib/api";
import { date as fmtDate, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Bid } from "@/lib/types";
import { timeLeft, useNow } from "@/lib/useNow";
import { IdempotentButton } from "../common/IdempotentButton";
import { StatusIcon } from "../common/StatusIcon";

/**
 * One financier's offer. Every figure is the server's. There is no "best" mark:
 * the list is only sorted by what you receive. The id is shown so a MOCK bid can
 * never pass for a real one.
 */
export function BidCard({
  bid,
  onSelect,
  disabled,
  version,
  offline,
  onConflict,
}: {
  bid: Bid;
  onSelect: (opts: MutationOptions) => Promise<void>;
  /** Another bid is being selected right now. */
  disabled: boolean;
  version: number | null;
  offline: boolean;
  onConflict: () => Promise<void> | void;
}) {
  const { t } = useT();
  const left = timeLeft(bid.valid_until, useNow());
  const expired = bid.status !== "AVAILABLE" || left?.expired === true;
  return (
    <li className={`panel flex flex-col gap-3 p-4 ${expired ? "bg-paper-sunk text-ink-600" : ""}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="font-semibold text-ink-950">{bid.financier_alias}</h4>
        <span className="font-mono text-xs text-ink-500">{bid.id}</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-ink-500">{t("early.bid.rate")}</dt>
          <dd className="font-mono">{pct(bid.annual_rate)}</dd>
        </div>
        <div>
          <dt className="text-ink-500">{t("early.bid.discount")}</dt>
          <dd className="font-mono">{money(bid.discount)}</dd>
        </div>
        <div>
          <dt className="text-ink-500">{t("early.bid.fee")}</dt>
          <dd className="font-mono">{money(bid.fee)}</dd>
        </div>
        <div>
          <dt className="font-medium text-ink-800">{t("early.bid.receive")}</dt>
          <dd className="font-mono text-base font-semibold text-ink-950">{money(bid.net_amount)}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {expired ? (
          <StatusIcon size="sm" tone="info" icon="clock" label={t("early.bid.expired")} />
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-ink-600">
            {left ? t("early.bid.left", { time: left.text }) : fmtDate(bid.valid_until.slice(0, 10))}
          </span>
        )}
        <IdempotentButton
          actionId={`bid.select:${bid.id}`}
          run={onSelect}
          version={version}
          onConflict={onConflict}
          offline={offline}
          disabled={expired || disabled}
          className="btn btn-secondary"
        >
          {t("early.bid.select")}
        </IdempotentButton>
      </div>
    </li>
  );
}
