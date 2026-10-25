"use client";

import Link from "next/link";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState } from "@/lib/params";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { EligibilityPill } from "./EligibilityPill";

export function CaseHeader({
  caseId,
  request,
  response,
  showViewToggle = true,
}: {
  caseId: string;
  request: CaseRequest | null;
  response: CaseResponse | null;
  showViewToggle?: boolean;
}) {
  const { t } = useT();
  const href = useHref();
  const { view } = useUrlState();

  return (
    <div className="no-print flex flex-col gap-4">
      <nav aria-label={t("nav.breadcrumb")} className="flex items-center gap-1.5 text-sm text-ink-500">
        <Link href={href("/", { view: "supplier" })} className="hover:text-ink-950">
          {t("nav.back_to_dues")}
        </Link>
        <Icon name="chevron" className="h-3.5 w-3.5 text-ink-300" />
        <span className="num truncate text-ink-700">{caseId}</span>
      </nav>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.025em] text-ink-950 sm:text-[2rem]">
            {request?.buyer.name ?? caseId}
          </h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-500">
            {request && <span>{request.supplier.name}</span>}
            {response && (
              <>
                <span aria-hidden="true" className="text-ink-300">·</span>
                <span className="num">{t("case.as_of", { date: date(response.calculation_date) })}</span>
                <EligibilityPill status={response.jurisdiction.status} />
              </>
            )}
          </div>
        </div>
        {showViewToggle && (
          <div role="group" aria-label={t("case.view.label")} className="inline-flex self-start rounded-lg border border-rule bg-paper-sunk p-0.5 sm:self-auto">
            {(["supplier", "cfo"] as const).map((v) => (
              <Link
                key={v}
                href={href(`/case/${caseId}`, { view: v })}
                aria-current={view === v ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  view === v ? "bg-paper-raised text-ink-950 shadow-[0_1px_2px_rgb(13_13_12/0.08)]" : "text-ink-500 hover:text-ink-950"
                }`}
              >
                {t(v === "supplier" ? "case.view.supplier" : "case.view.cfo")}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
