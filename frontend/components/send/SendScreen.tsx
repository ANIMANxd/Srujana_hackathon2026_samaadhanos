"use client";

import Link from "next/link";
import { isPlaceholder } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { useEvaluation } from "@/lib/useEvaluation";
import type { Stage } from "@/lib/types";
import { Icon } from "../common/Icon";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { DataBanners } from "../shell/Banners";
import { JudgeConsole } from "../shell/JudgeConsole";
import { CaseHeader } from "../case/CaseHeader";
import { SendPanel } from "./SendPanel";

/** /case/[id]/send/[stage]: the same draft panel as the case screen's drawer, as a full page. */
export function SendScreen({ caseId, stage }: { caseId: string; stage: Stage }) {
  const { t } = useT();
  const href = useHref();
  const ev = useEvaluation(caseId);
  const res = ev.response;
  const req = ev.request;

  if (ev.status === "not_found") return <NotFoundState />;

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={req} response={res} showViewToggle={false} />
      <DataBanners placeholder={isPlaceholder(res)} needsBackend={ev.status === "needs_backend"} />
      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}

      {stage === 4 ? (
        <div className="panel flex flex-col items-start gap-4 p-6">
          <p className="text-ink-800">{t("send.stage4_redirect")}</p>
          <Link href={href(`/case/${caseId}/pack`)} className="btn btn-primary">{t("stage.4.button")}</Link>
        </div>
      ) : (
        res &&
        req &&
        ev.status !== "needs_backend" && (
          <section aria-labelledby="send-title" className="panel flex flex-col gap-6 p-6 sm:p-8">
            <h2 id="send-title" className="text-xl font-semibold tracking-[-0.015em] text-ink-950">
              {t("send.title", { n: stage, title: t(`stage.${stage}.title`) })}
            </h2>
            <SendPanel caseId={caseId} stage={stage} request={req} response={res} offlineId={ev.offlineId} tracking={ev.tracking} />
          </section>
        )
      )}

      <Link href={href(`/case/${caseId}`)} className="btn btn-quiet self-start">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("nav.back_to_case")}
      </Link>
      <JudgeConsole current={null} />
    </div>
  );
}
