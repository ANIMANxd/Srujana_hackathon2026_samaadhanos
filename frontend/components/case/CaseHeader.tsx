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
    <div className="no-print flex flex-col gap-3">
      <Link href={href("/", { view: "supplier" })} className="inline-flex items-center gap-1.5 self-start text-sm font-medium text-ink-700 hover:text-ink-950">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("nav.back_to_dues")}
      </Link>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="font-display text-3xl font-bold leading-tight tracking-tight text-ink-950">
            {request?.buyer.name ?? caseId}
          </h1>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-600">
            <span className="num">{t("case.case_id", { id: caseId })}</span>
            {response && <span>{t("case.calc_date", { date: date(response.calculation_date) })}</span>}
            {response && <EligibilityPill status={response.jurisdiction.status} />}
          </p>
        </div>
        {showViewToggle && (
          <div role="group" aria-label={t("case.view.label")} className="inline-flex self-start rounded-md border border-rule-strong bg-paper-raised p-1 sm:self-auto">
            {(["supplier", "cfo"] as const).map((v) => (
              <Link
                key={v}
                href={href(`/case/${caseId}`, { view: v })}
                aria-current={view === v ? "page" : undefined}
                className={`rounded-sm px-3 py-1.5 text-sm font-semibold ${view === v ? "bg-ink-900 text-paper" : "text-ink-700 hover:text-ink-950"}`}
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
