"use client";

import Link from "next/link";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { PersonaSwitch } from "../shell/PersonaSwitch";
import { EligibilityPill } from "./EligibilityPill";

export function CaseHeader({
  caseId,
  request,
  response,
  showViewToggle = true,
  linkEligibility = true,
}: {
  caseId: string;
  request: CaseRequest | null;
  response: CaseResponse | null;
  showViewToggle?: boolean;
  /** False on the eligibility panel itself, so the pill does not link to its own page. */
  linkEligibility?: boolean;
}) {
  const { t } = useT();
  const href = useHref();

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
                <EligibilityPill status={response.jurisdiction.status} caseId={linkEligibility ? caseId : undefined} />
              </>
            )}
          </div>
        </div>
        {showViewToggle && <PersonaSwitch path={`/case/${caseId}`} />}
      </div>
    </div>
  );
}
