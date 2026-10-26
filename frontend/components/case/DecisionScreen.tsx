"use client";

import Link from "next/link";
import { currentStage, isPlaceholder } from "@/lib/derive";
import { count, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import type { TrackView } from "@/lib/useTrack";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { ChoiceCard } from "../options/ChoiceCard";
import { Banner } from "../shell/Banners";

/**
 * The page a stored case opens on: who owes what, then the two ways forward,
 * each with one button. Everything else (timeline, interest ledger, time limit,
 * assumptions, the four-step ladder) lives behind "Full details".
 */
export function DecisionScreen({
  caseId,
  request,
  response,
  tracking,
  onDetails,
}: {
  caseId: string;
  request: CaseRequest;
  response: CaseResponse;
  tracking: TrackView;
  onDetails: () => void;
}) {
  const { t } = useT();
  const href = useHref();
  const fin = response.financials;
  const days = response.timeline?.days_overdue ?? null;
  const overdue = days !== null && days > 0;
  const placeholder = isPlaceholder(response);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <nav aria-label={t("nav.breadcrumb")} className="text-sm text-ink-500">
          <Link href={href("/")} className="hover:text-ink-950">
            {t("nav.back_to_dues")}
          </Link>
        </nav>
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.025em] text-ink-950 sm:text-[2rem]">{request.buyer.name}</h1>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-600">
          <span className="num">{tracking.caseDetail?.case.invoice_no ?? caseId}</span>
          {overdue ? (
            <StatusIcon size="sm" tone="warn" icon="clock" label={t("hero.overdue", { n: count(days) })} />
          ) : fin ? (
            <StatusIcon size="sm" tone="ok" label={t("hero.not_due")} />
          ) : null}
        </p>
      </header>

      {tracking.source === "offline" && <Banner tone="warn" icon="lock" message="track.offline_sample" />}
      {placeholder && <Banner tone="warn" icon="warn" message="banner.placeholder" />}

      {fin ? (
        <section aria-labelledby="owed" className="rounded-xl border border-rule bg-paper-raised p-5 sm:p-6">
          <p id="owed" className="text-sm text-ink-600">
            {t("decision.owed")}
          </p>
          <p className="figure mt-1 text-4xl font-semibold text-ink-950 sm:text-5xl">{money(fin.total_claim)}</p>
          <p className="mt-2 text-sm text-ink-600">
            {t("decision.breakdown", { principal: money(fin.principal_outstanding), interest: money(fin.interest_outstanding) })}
          </p>
        </section>
      ) : (
        <p className="rounded-xl border border-rule bg-paper-raised p-5 text-sm text-ink-700">{t("hero.no_money_body")}</p>
      )}

      <section aria-labelledby="choose" className="flex flex-col gap-3">
        <h2 id="choose" className="text-base font-semibold text-ink-950">
          {t("decision.choose")}
        </h2>
        <ChoiceCard caseId={caseId} tracking={tracking} stage={currentStage(response)} request={request} response={response} />
      </section>

      <div>
        <button type="button" onClick={onDetails} className="btn btn-quiet">
          {t("decision.details")}
          <Icon name="chevron-down" className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
