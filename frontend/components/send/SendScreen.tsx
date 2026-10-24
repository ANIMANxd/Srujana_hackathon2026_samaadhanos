"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { generateArtifact, type ArtifactKind } from "@/lib/api";
import { logPrepared } from "@/lib/caseStore";
import { isPlaceholder, isStageBlocked, latestSegment } from "@/lib/derive";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { useEvaluation } from "@/lib/useEvaluation";
import type { CaseRequest, CaseResponse, Stage } from "@/lib/types";
import { Icon } from "../common/Icon";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner, DataBanners } from "../shell/Banners";
import { CaseHeader } from "../case/CaseHeader";

const KIND: Record<1 | 2 | 3, ArtifactKind> = {
  1: "STAGE1_BALANCE_CONFIRMATION",
  2: "STAGE2_CFO_MEMO",
  3: "STAGE3_SETTLEMENT_TERMSHEET",
};

const TEMPLATE: Record<1 | 2 | 3, MessageKey> = { 1: "tpl.1", 2: "tpl.2", 3: "tpl.3" };

const PHONE = /^\d{8,15}$/;

function todayLocal(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Fallback draft filled ONLY with engine numbers and request inputs. */
function fallbackDraft(
  t: (k: MessageKey, v?: Record<string, string | number>) => string,
  stage: 1 | 2 | 3,
  req: CaseRequest,
  res: CaseResponse,
): string {
  const fin = res.financials;
  const seg = latestSegment(fin);
  return t(TEMPLATE[stage], {
    buyer: req.buyer.name,
    supplier: req.supplier.name,
    principal: money(fin?.principal_outstanding ?? req.transaction.principal),
    interest: money(fin?.interest_outstanding ?? null),
    rate: seg ? pct(seg.statutory_rate_pct) : "—",
    delivery: date(res.timeline?.delivery_date ?? req.transaction.delivery_date ?? null),
  });
}

/** F11: editable draft, then the owner opens their own app. Nothing auto-sends. */
export function SendScreen({ caseId, stage }: { caseId: string; stage: Stage }) {
  const { t } = useT();
  const href = useHref();
  const ev = useEvaluation(caseId);
  const [draft, setDraft] = useState<string | null>(null);
  const [isFallback, setIsFallback] = useState(false);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [subjectEdit, setSubject] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [copied, setCopied] = useState(false);

  const res = ev.response;
  const req = ev.request;
  const subject = subjectEdit ?? (req ? t("send.subject_default", { supplier: req.supplier.name }) : "");

  useEffect(() => {
    if (!res || !req || stage === 4 || draft !== null) return;
    let alive = true;
    generateArtifact(KIND[stage], req)
      .then((a) => {
        if (!alive) return;
        if (a) {
          setDraft(a.markdown);
          setIsFallback(false);
        } else {
          setDraft(fallbackDraft(t, stage, req, res));
          setIsFallback(true);
        }
      })
      .catch(() => {
        if (!alive) return;
        setDraft(fallbackDraft(t, stage, req, res));
        setIsFallback(true);
      });
    return () => {
      alive = false;
    };
  }, [res, req, stage, draft, t]);

  if (ev.status === "not_found") return <NotFoundState />;

  if (stage === 4) {
    return (
      <div className="flex flex-col gap-4">
        <CaseHeader caseId={caseId} request={req} response={res} showViewToggle={false} />
        <p className="text-ink-800">{t("send.stage4_redirect")}</p>
        <Link href={href(`/case/${caseId}/pack`)} className="btn btn-primary self-start">{t("stage.4.button")}</Link>
      </div>
    );
  }

  const blocked = res ? isStageBlocked(res, stage) : false;
  const phoneValid = phone === "" || PHONE.test(phone);
  const text = draft ?? "";
  const waHref = `https://wa.me/${phoneValid ? phone : ""}?text=${encodeURIComponent(text)}`;
  const mailHref = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
  const canSend = reviewed && text.trim().length > 0 && !blocked;

  const prepared = () => logPrepared(caseId, stage, todayLocal());

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      prepared();
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={req} response={res} showViewToggle={false} />
      <DataBanners offline={ev.source === "offline"} placeholder={isPlaceholder(res)} needsBackend={ev.status === "needs_backend"} />
      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}

      {res && req && (
        <section aria-labelledby="send-title" className="panel flex flex-col gap-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="send-title" className="font-display text-2xl font-semibold text-ink-950">
              {t("send.title", { n: stage, title: t(`stage.${stage}.title`) })}
            </h2>
            <StatusIcon tone="info" icon="doc" label={t("badge.draft")} />
          </div>
          <p className="text-ink-700">{t(`stage.${stage}.purpose`)}</p>

          {blocked ? (
            <Banner tone="block" icon="lock" message="send.blocked" />
          ) : (
            <>
              {isFallback && <Banner tone="warn" icon="warn" message="send.placeholder_draft" />}
              <label className="flex flex-col">
                <span className="field-label">{t("send.draft_label")}</span>
                {draft === null ? (
                  <div className="h-56 animate-pulse rounded-sm bg-paper-sunk" aria-hidden="true" />
                ) : (
                  <textarea
                    className="field-input min-h-72 font-sans leading-relaxed"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                  />
                )}
              </label>

              <div className="grid gap-4 sm:grid-cols-3">
                <label>
                  <span className="field-label">{t("send.phone")}</span>
                  <input className="field-input num" inputMode="numeric" value={phone} aria-invalid={!phoneValid} aria-describedby="phone-hint" onChange={(e) => setPhone(e.target.value.replace(/\s/g, ""))} />
                  <span id="phone-hint" className={`mt-1 block text-xs ${phoneValid ? "text-ink-600" : "text-block"}`}>
                    {t(phoneValid ? "send.phone_hint" : "send.phone_invalid")}
                  </span>
                </label>
                <label>
                  <span className="field-label">{t("send.email")}</span>
                  <input className="field-input" type="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} />
                </label>
                <label>
                  <span className="field-label">{t("send.subject")}</span>
                  <input className="field-input" value={subject} onChange={(e) => setSubject(e.target.value)} />
                </label>
              </div>

              <label className="flex items-start gap-3 rounded-md border border-rule bg-paper px-4 py-3">
                <input type="checkbox" className="mt-0.5 h-5 w-5" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
                <span className="font-medium text-ink-900">{t("send.reviewed")}</span>
              </label>

              <div className="flex flex-wrap gap-3">
                <a
                  href={canSend && phoneValid ? waHref : undefined}
                  aria-disabled={!canSend || !phoneValid}
                  target="_blank"
                  rel="noreferrer noopener"
                  onClick={(e) => (canSend && phoneValid ? prepared() : e.preventDefault())}
                  className="btn btn-primary"
                >
                  <Icon name="send" className="h-4 w-4" />
                  {t("send.open_whatsapp")}
                </a>
                <a
                  href={canSend ? mailHref : undefined}
                  aria-disabled={!canSend}
                  onClick={(e) => (canSend ? prepared() : e.preventDefault())}
                  className="btn btn-secondary"
                >
                  <Icon name="doc" className="h-4 w-4" />
                  {t("send.open_email")}
                </a>
                <button type="button" className="btn btn-secondary" disabled={!canSend} onClick={copy}>
                  <Icon name="copy" className="h-4 w-4" />
                  {copied ? t("send.copied") : t("send.copy")}
                </button>
              </div>
              <p className="flex items-center gap-2 text-sm font-medium text-ink-800">
                <Icon name="lock" className="h-4 w-4" />
                {t("send.disclaimer")}
              </p>
            </>
          )}
        </section>
      )}

      <Link href={href(`/case/${caseId}`)} className="btn btn-quiet self-start">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("nav.back_to_case")}
      </Link>
    </div>
  );
}
