"use client";

// One customer (or one group of customers) on the Dues home. Descriptive
// figures from the owner's own records only: what is owed, what the law adds,
// how long payments have taken and how many arrived by the legal due date.
// No score, rank or label about the buyer. Every figure is the server's.

import Link from "next/link";
import { useId, useState } from "react";
import { trackChip, type Chip } from "@/lib/dueChip";
import { approxDays, count, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import type { RowDetail } from "@/lib/useCustomerDetails";
import type { CustomerGroupRow, CustomerRow } from "@/lib/types";
import { LiveInterestTicker } from "../case/LiveInterestTicker";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

export const BOOK_GRID =
  "lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1.35fr)_minmax(0,1fr)_minmax(0,1.4fr)_4.5rem]";

const MAX_CHIPS = 2;

function chipLabel(chip: Chip, t: ReturnType<typeof useT>["t"]): string {
  return chip.prefix ? `${t(chip.prefix)} · ${t(chip.status as MessageKey, chip.vars)}` : t(chip.status as MessageKey);
}

/** A cell with its column name for screen readers (and as a caption on small screens). */
function Cell({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 text-sm ${className}`}>
      <span className="text-[0.6875rem] text-ink-500 lg:sr-only">{label}</span>
      {children}
    </div>
  );
}

function PaysIn({ detail, legalLimit }: { detail: RowDetail; legalLimit: string | null }) {
  const { t } = useT();
  const f = detail.avgDaysToPay;
  const basedOn = t("customers.based_on", { n: count(f.basedOn) });
  if (f.kind === "not_enough") {
    return (
      <>
        <span className="text-ink-600">{t("customers.not_enough")}</span>
        <span className="text-xs text-ink-500">{basedOn}</span>
      </>
    );
  }
  return (
    <>
      <span className="num text-ink-950">{t("customers.pays_in", { n: approxDays(f.value) })}</span>
      <span className="text-xs text-ink-500">
        {legalLimit ? `${t("customers.legal_limit", { n: legalLimit })} · ` : ""}
        {basedOn}
      </span>
    </>
  );
}

function OnTime({ detail }: { detail: RowDetail }) {
  const { t } = useT();
  const f = detail.onTimePct;
  return (
    <>
      <span className={f.kind === "value" ? "num text-ink-950" : "text-ink-600"}>
        {f.kind === "value" ? t("customers.on_time_pct", { pct: pct(f.value) }) : t("customers.not_enough")}
      </span>
      <span className="text-xs text-ink-500">{t("customers.based_on", { n: count(f.basedOn) })}</span>
    </>
  );
}

function Interest({ detail }: { detail: RowDetail }) {
  const { t } = useT();
  const i = detail.interest;
  if (i.kind === "single") return <LiveInterestTicker interest={i.interest} dailyAccrual={i.dailyAccrual} className="text-ink-950" />;
  if (i.kind === "several") return <span className="text-ink-600">{t("customers.interest_several", { n: count(i.invoices) })}</span>;
  if (i.kind === "none") return <span className="text-ink-500">{t("customers.interest_none")}</span>;
  return <span className="text-ink-500">{t("customers.interest_unknown")}</span>;
}

function Chips({ detail }: { detail: RowDetail }) {
  const { t } = useT();
  if (detail.cases.length === 0) return <span className="text-ink-500">{t("customers.no_cases")}</span>;
  const seen = new Map<string, Chip>();
  for (const c of detail.cases) {
    const chip = trackChip(c.active_track);
    const label = chipLabel(chip, t);
    if (!seen.has(label)) seen.set(label, chip);
  }
  const chips = [...seen.entries()];
  return (
    <span className="flex flex-wrap items-center gap-1">
      {chips.slice(0, MAX_CHIPS).map(([label, chip]) => (
        <StatusIcon key={label} size="sm" wrap tone={chip.tone} icon={chip.icon} label={label} />
      ))}
      {chips.length > MAX_CHIPS && <span className="text-xs text-ink-500">{t("customers.chip_more", { n: count(chips.length - MAX_CHIPS) })}</span>}
    </span>
  );
}

export function CustomerLine({
  row,
  detail,
  placeholder,
  legalLimit,
  nested = false,
}: {
  row: CustomerRow;
  /** undefined: still loading; null: no profile could be read. */
  detail: RowDetail | null | undefined;
  placeholder: boolean;
  legalLimit: string | null;
  nested?: boolean;
}) {
  const { t } = useT();
  const href = useHref();
  const loading = <Skeleton className="h-4 w-20" />;
  const none = <span className="text-ink-500">—</span>;
  const sub =
    row.gstin_count > 1 ? t("customers.gstins", { n: count(row.gstin_count) }) : row.kind === "PROVISIONAL" ? t("customers.no_pan") : (row.pan ?? "");

  return (
    <li className={`grid grid-cols-2 items-start gap-x-4 gap-y-3 px-5 py-4 sm:grid-cols-3 ${BOOK_GRID} ${nested ? "bg-paper/60" : ""}`}>
      <div className={`col-span-2 flex min-w-0 flex-col gap-0.5 sm:col-span-3 lg:col-span-1 ${nested ? "border-l-2 border-rule pl-3 lg:ml-6" : ""}`}>
        <span className="line-clamp-2 font-medium text-ink-950" title={row.display_name}>{row.display_name}</span>
        {sub && <span className="num truncate text-xs text-ink-500">{sub}</span>}
      </div>
      <Cell label={t("customers.col.outstanding")} className="lg:items-end lg:text-right">
        <Money value={row.outstanding_total} className="font-medium text-ink-950" />
        {placeholder && <PlaceholderBadge />}
      </Cell>
      <Cell label={t("customers.col.overdue")} className="lg:items-end lg:text-right">
        <Money value={row.overdue_total} className={row.oldest_overdue_days ? "text-warn" : "text-ink-700"} />
        {row.oldest_overdue_days ? (
          <span className="inline-flex items-center gap-1 text-xs text-warn">
            <Icon name="clock" className="h-3 w-3" />
            {t("dues.row.overdue", { n: count(row.oldest_overdue_days) })}
          </span>
        ) : null}
        {placeholder && <PlaceholderBadge />}
      </Cell>
      <Cell label={t("customers.col.interest")} className="lg:items-end lg:text-right">
        {detail === undefined ? loading : detail === null ? none : <Interest detail={detail} />}
      </Cell>
      <Cell label={t("customers.col.pays_in")}>{detail === undefined ? loading : detail === null ? none : <PaysIn detail={detail} legalLimit={legalLimit} />}</Cell>
      <Cell label={t("customers.col.on_time")}>{detail === undefined ? loading : detail === null ? none : <OnTime detail={detail} />}</Cell>
      <Cell label={t("customers.col.track")} className="col-span-2 sm:col-span-1">
        {detail === undefined ? loading : detail === null ? none : <Chips detail={detail} />}
      </Cell>
      <div className="col-span-2 flex justify-start sm:col-span-3 lg:col-span-1 lg:justify-end">
        <Link
          href={href(`/customers/${encodeURIComponent(row.id)}`)}
          aria-label={t("customers.open_label", { name: row.display_name })}
          className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-sm font-medium text-ink-800 hover:bg-paper-sunk hover:text-ink-950"
        >
          {t("customers.open")}
          <Icon name="arrow-right" className="h-3.5 w-3.5" />
        </Link>
      </div>
    </li>
  );
}

export function GroupLine({
  group,
  rows,
  details,
  placeholder,
  legalLimit,
}: {
  group: CustomerGroupRow;
  rows: CustomerRow[];
  details: Map<string, RowDetail | null>;
  placeholder: boolean;
  legalLimit: string | null;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const listId = useId();
  const companies = Math.max(group.member_count, rows.length);
  const perCompany = <span className="text-xs text-ink-500">{t(open ? "customers.group_per_company_open" : "customers.group_per_company")}</span>;

  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={t(open ? "customers.group_collapse" : "customers.group_expand", { name: group.label })}
        onClick={() => setOpen((v) => !v)}
        className={`grid w-full grid-cols-2 items-start gap-x-4 gap-y-2 px-5 py-4 text-left transition-colors hover:bg-paper sm:grid-cols-3 ${BOOK_GRID}`}
      >
        <span className="col-span-2 flex min-w-0 items-start gap-2 sm:col-span-3 lg:col-span-1">
          <Icon name="chevron-down" className={`mt-1 h-4 w-4 shrink-0 text-ink-500 transition-transform ${open ? "" : "-rotate-90"}`} />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="line-clamp-2 font-medium text-ink-950">{group.label}</span>
            <span className="text-xs text-ink-500">{t("customers.group_meta", { n: count(companies) })}</span>
          </span>
        </span>
        <span className="col-span-2 self-center sm:col-span-3 lg:col-span-7">{perCompany}</span>
      </button>
      <ul id={listId} hidden={!open} className="divide-y divide-rule border-t border-rule">
        {rows.map((r) => (
          <CustomerLine key={r.id} row={r} detail={details.get(r.id)} placeholder={placeholder} legalLimit={legalLimit} nested />
        ))}
      </ul>
    </li>
  );
}
