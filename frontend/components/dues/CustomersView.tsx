"use client";

// The customer-first Dues view: insights on top, a duplicates banner when the
// server has suggestions, then one row per customer or group. The server sorts;
// this screen only arranges rows into their groups.

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import type { CustomerSort, SortDir } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { configText, useConfig } from "@/lib/useConfig";
import { useCustomerDetails } from "@/lib/useCustomerDetails";
import { useCustomers } from "@/lib/useCustomers";
import { useInsights } from "@/lib/useInsights";
import { Icon } from "../common/Icon";
import { EmptyState, ErrorState, Skeleton } from "../common/States";
import { Banner, DataBanners } from "../shell/Banners";
import { SuggestionsDrawer } from "../customers/SuggestionsDrawer";
import { BOOK_GRID, CustomerLine, GroupLine } from "./CustomerBookRow";
import { InsightsStrip } from "./InsightsStrip";

/** The sort menu: each entry has the direction that reads naturally for it. */
const SORTS: { sort: CustomerSort; dir: SortDir; label: MessageKey }[] = [
  { sort: "outstanding_total", dir: "desc", label: "customers.sort.outstanding_total" },
  { sort: "overdue_total", dir: "desc", label: "customers.sort.overdue_total" },
  { sort: "avg_days_to_pay", dir: "desc", label: "customers.sort.avg_days_to_pay" },
  { sort: "display_name", dir: "asc", label: "customers.sort.display_name" },
];

export function CustomersView({ demoButton }: { demoButton: ReactNode }) {
  const { t } = useT();
  const href = useHref();
  const [choice, setChoice] = useState(0);
  const { sort, dir } = SORTS[choice];
  const book = useCustomers({ sort, dir, grouped: true });
  const insights = useInsights();
  const { config } = useConfig();
  const legalLimit = configText(config, "credit_cap_days");
  const ids = useMemo(() => (book.rows ?? []).map((r) => r.id), [book.rows]);
  const details = useCustomerDetails(ids, book.source);
  const placeholder = book.placeholder || insights.placeholder;

  return (
    <div className="flex flex-col gap-5">
      {book.source === "offline" && <Banner tone="warn" icon="lock" message="book.offline_sample" />}
      <DataBanners placeholder={placeholder} />
      <InsightsStrip insights={insights} />
      <SuggestionsDrawer />

      {book.error && !book.rows ? (
        <ErrorState message={book.error.detail ?? t(book.error.key)} onRetry={book.refresh} />
      ) : book.rows === null || book.sections === null ? (
        <div className="panel flex flex-col gap-3 p-5" aria-busy="true">
          <span className="sr-only">{t("state.loading")}</span>
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : book.rows.length === 0 ? (
        <EmptyState title={t("customers.empty.title")} body={t("customers.empty.body")}>
          <Link href={href("/upload")} className="btn btn-primary">
            <Icon name="upload" className="h-4 w-4" />
            {t("customers.empty.import")}
          </Link>
          {demoButton}
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-ink-500">{t("customers.group_note")}</p>
            <label className="inline-flex items-center gap-2 text-sm text-ink-700">
              {t("customers.sort_label")}
              <select
                value={choice}
                onChange={(e) => setChoice(Number(e.target.value))}
                className="min-h-9 rounded-md border border-rule bg-white px-2.5 text-sm text-ink-950"
              >
                {SORTS.map((s, i) => (
                  <option key={s.sort} value={i}>
                    {t(s.label)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="panel overflow-hidden">
            <div className={`hidden gap-x-4 border-b border-rule bg-paper px-5 py-2.5 text-xs font-medium text-ink-500 lg:grid ${BOOK_GRID}`} aria-hidden="true">
              <span>{t("customers.col.customer")}</span>
              <span className="text-right">{t("customers.col.outstanding")}</span>
              <span className="text-right">{t("customers.col.overdue")}</span>
              <span className="text-right">{t("customers.col.interest")}</span>
              <span>{t("customers.col.pays_in")}</span>
              <span>{t("customers.col.on_time")}</span>
              <span>{t("customers.col.track")}</span>
              <span />
            </div>
            <ul aria-label={t("customers.list_label")} className="divide-y divide-rule">
              {book.sections.map((s) =>
                s.kind === "group" ? (
                  <GroupLine key={s.group.id} group={s.group} rows={s.rows} details={details} placeholder={placeholder} legalLimit={legalLimit} />
                ) : (
                  s.rows.map((r) => <CustomerLine key={r.id} row={r} detail={details.get(r.id)} placeholder={placeholder} legalLimit={legalLimit} />)
                ),
              )}
            </ul>
          </div>
          <p className="text-xs text-ink-500">
            {t("stats.days_from_acceptance")} {t("stats.on_time_rule")}
          </p>
        </div>
      )}
    </div>
  );
}
