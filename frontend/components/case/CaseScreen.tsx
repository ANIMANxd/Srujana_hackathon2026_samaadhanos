"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSendLog } from "@/lib/caseStore";
import { isNotCovered, isPlaceholder } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState } from "@/lib/params";
import { useConfig } from "@/lib/useConfig";
import { useEvaluation } from "@/lib/useEvaluation";
import { Drawer } from "../common/Drawer";
import { Icon } from "../common/Icon";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { DataBanners } from "../shell/Banners";
import { JudgeConsole, judgeCase } from "../shell/JudgeConsole";
import { CfoCostLines } from "../cfo/CfoCostLines";
import { SendPanel } from "../send/SendPanel";
import { AssumptionsDrawer } from "./AssumptionsDrawer";
import { CaseHeader } from "./CaseHeader";
import { CaseTabs } from "./CaseTabs";
import { EvidenceTab } from "../evidence/EvidenceTab";
import { MathTab } from "../math/MathTab";
import { EscalationLadder } from "./EscalationLadder";
import { GuidanceCard } from "./GuidanceCard";
import { LimitationCard } from "./LimitationCard";
import { MoneyCard } from "./MoneyCard";
import { NotCovered } from "./NotCovered";
import { StatuteTimeline } from "./StatuteTimeline";

/** The hero screen (frontend-structure §2): claim, timeline, money, next step. */
export function CaseScreen({ caseId }: { caseId: string }) {
  const { t } = useT();
  const href = useHref();
  const router = useRouter();
  const { view, send, tab } = useUrlState();
  const ev = useEvaluation(caseId);
  const cfg = useConfig();
  const log = useSendLog(caseId);

  const judge = judgeCase(ev);

  if (ev.status === "not_found") return <NotFoundState />;

  const res = ev.response;
  const placeholder = isPlaceholder(res);
  const notCovered = res ? isNotCovered(res) : false;
  const closeSend = () => router.replace(href(`/case/${caseId}`, { tab }), { scroll: false });

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={ev.request} response={res} showViewToggle={Boolean(res)} />
      <DataBanners placeholder={placeholder} needsBackend={ev.status === "needs_backend"} />
      {ev.error && res && <ErrorState message={ev.error} onRetry={ev.retry} />}

      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}
      {ev.status === "needs_backend" && (
        <div className="flex flex-wrap gap-2">
          {ev.isEdited && (
            <button type="button" className="btn btn-secondary" onClick={ev.reset}>
              {t("judge.reset")}
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={ev.retry}>
            {t("state.retry")}
          </button>
        </div>
      )}

      {res && ev.request && ev.status !== "needs_backend" && (
        <div className={`flex flex-col gap-4 transition-opacity ${ev.refreshing ? "opacity-70" : ""}`} aria-busy={ev.refreshing}>
          {view === "cfo" ? (
            <CfoCostLines caseId={caseId} request={ev.request} response={res} placeholder={placeholder} onChangeRequest={ev.setRequest} />
          ) : notCovered ? (
            <NotCovered request={ev.request} response={res} />
          ) : (
            <>
              {res.jurisdiction.status === "INSUFFICIENT_DATA" && (
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-600">
                  <Icon name="info" className="h-4 w-4 text-warn" />
                  {t("eligibility.unconfirmed_note")}
                  <Link href={href(`/eligibility/${caseId}`)} className="link">
                    {t("eligibility.see_why")}
                  </Link>
                </p>
              )}
              <CaseTabs caseId={caseId} />
              {tab === "evidence" && ev.base ? (
                <EvidenceTab caseId={caseId} request={ev.request} base={ev.base} response={res} onChange={ev.setRequest} />
              ) : tab === "math" ? (
                <MathTab
                  request={ev.request}
                  response={res}
                  placeholder={placeholder}
                  config={cfg.config}
                  configLoading={cfg.loading}
                  configIsStub={cfg.isStub}
                  onChange={ev.setRequest}
                />
              ) : (
                <>
                  <GuidanceCard caseId={caseId} response={res} config={cfg.config} placeholder={placeholder} />
                  <StatuteTimeline response={res} />
                  <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
                    <MoneyCard response={res} placeholder={placeholder} />
                    <div className="flex flex-col gap-4">
                      <LimitationCard limitation={res.limitation} />
                      <AssumptionsDrawer response={res} config={cfg.config} configLoading={cfg.loading} configIsStub={cfg.isStub} />
                    </div>
                  </div>
                  <EscalationLadder caseId={caseId} response={res} log={log} />
                </>
              )}
            </>
          )}
        </div>
      )}

      {res && ev.request && !notCovered && send && (
        <Drawer open onClose={closeSend} title={t("send.title", { n: send, title: t(`stage.${send}.title`) })} width="md">
          <SendPanel key={send} caseId={caseId} stage={send} request={ev.request} response={res} offlineId={ev.offlineId} />
        </Drawer>
      )}

      <JudgeConsole current={judge} />
    </div>
  );
}
