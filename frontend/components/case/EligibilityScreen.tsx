"use client";

import { isPlaceholder } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useEvaluation } from "@/lib/useEvaluation";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { DataBanners } from "../shell/Banners";
import { CaseHeader } from "./CaseHeader";
import { NotCovered } from "./NotCovered";

/** /eligibility/[id]: "Does the law cover me?" as a full screen. */
export function EligibilityScreen({ caseId }: { caseId: string }) {
  const { t } = useT();
  const ev = useEvaluation(caseId);
  if (ev.status === "not_found") return <NotFoundState />;
  const res = ev.response;
  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={ev.request} response={res} showViewToggle={false} />
      <DataBanners offline={ev.source === "offline"} placeholder={isPlaceholder(res)} needsBackend={ev.status === "needs_backend"} />
      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}
      {res && ev.request && ev.status !== "needs_backend" && <NotCovered request={ev.request} response={res} />}
    </div>
  );
}
