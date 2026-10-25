"use client";

import { useEffect, useState } from "react";
import { ApiError, generateArtifact, type SourcedArtifact } from "@/lib/api";
import { logPrepared } from "@/lib/caseStore";
import { evidencePresent, isStageBlocked } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import type { ArtifactKind, CaseRequest, CaseResponse } from "@/lib/types";
import type { SendStage } from "@/lib/params";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";

const PHONE = /^\d{8,15}$/;

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Stage 1 asks for receipt first when there is no delivery proof (B8). */
function kindFor(stage: SendStage, req: CaseRequest, res: CaseResponse): ArtifactKind {
  if (stage === 2) return "STAGE2_CFO_MEMO";
  if (stage === 3) return "STAGE3_SETTLEMENT_TERMSHEET";
  const noProof = !evidencePresent(req, "DELIVERY_PROOF") || res.timeline?.objection_status === "NO_DELIVERY_PROOF";
  return noProof ? "STAGE1_ACCEPTANCE_NOTE" : "STAGE1_BALANCE_CONFIRMATION";
}

type Draft =
  | { state: "loading" }
  | { state: "ready"; artifact: SourcedArtifact; text: string }
  | { state: "needs_backend" }
  | { state: "error"; message: string };

/**
 * F11: the engine drafts, the owner edits and opens their own app.
 * Nothing auto-sends: every send button stays disabled until "I have read this".
 */
export function SendPanel({
  caseId,
  stage,
  request,
  response,
  offlineId,
}: {
  caseId: string;
  stage: SendStage;
  request: CaseRequest;
  response: CaseResponse;
  offlineId: string | null;
}) {
  const { t, tCode } = useT();
  const kind = kindFor(stage, request, response);
  const [draft, setDraft] = useState<Draft>({ state: "loading" });
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [subjectEdit, setSubject] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    generateArtifact(kind, request, offlineId)
      .then((a) => {
        if (!alive) return;
        setDraft(a ? { state: "ready", artifact: a, text: a.data.markdown } : { state: "needs_backend" });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setDraft({ state: "error", message: e instanceof ApiError ? e.message : t("state.error_title") });
      });
    return () => {
      alive = false;
    };
  }, [kind, request, offlineId, t]);

  const blocked = isStageBlocked(response, stage);
  const subject = subjectEdit ?? t("send.subject_default", { title: t(`stage.${stage}.title`), supplier: request.supplier.name });
  const text = draft.state === "ready" ? draft.text : "";
  const phoneValid = phone === "" || PHONE.test(phone);
  const canSend = reviewed && text.trim().length > 0 && !blocked;
  const waHref = `https://wa.me/${phoneValid ? phone : ""}?text=${encodeURIComponent(text)}`;
  const mailHref = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
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

  if (blocked) return <Banner tone="block" icon="lock" message="send.blocked" />;

  const artifact = draft.state === "ready" ? draft.artifact : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <StatusIcon size="sm" tone="info" icon="doc" label={t("badge.draft")} />
        <p className="text-sm text-ink-600">{t(`stage.${stage}.purpose`)}</p>
      </div>

      {artifact?.source === "offline" && <Banner tone="info" icon="info" message="send.sample_draft" />}
      {draft.state === "needs_backend" && <Banner tone="warn" icon="lock" message="send.needs_backend" />}
      {draft.state === "error" && (
        <div role="alert" className="rounded-lg border border-block/25 bg-block-wash px-3.5 py-2 text-sm text-block">
          {draft.message}
        </div>
      )}

      <label className="flex flex-col">
        <span className="field-label">{t("send.draft_label")}</span>
        {draft.state === "loading" ? (
          <div className="flex h-72 items-center justify-center rounded-lg border border-rule bg-paper text-sm text-ink-500" aria-busy="true">
            {t("send.loading")}
          </div>
        ) : (
          <textarea
            className="field-input min-h-80 font-mono text-[0.8125rem] leading-relaxed"
            value={text}
            disabled={draft.state !== "ready"}
            onChange={(e) => draft.state === "ready" && setDraft({ ...draft, text: e.target.value })}
          />
        )}
      </label>

      {artifact && (artifact.data.warnings ?? []).length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs font-medium text-ink-600 hover:text-ink-950">{t("send.notes")}</summary>
          <ul className="mt-2 flex flex-col gap-1.5 text-ink-700">
            {(artifact.data.warnings ?? []).map((w, i) => (
              <li key={`${w.code}-${i}`}>{tCode("warning", w.code, w.text)}</li>
            ))}
          </ul>
        </details>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <label>
          <span className="field-label">{t("send.phone")}</span>
          <input
            className="field-input num"
            inputMode="numeric"
            value={phone}
            aria-invalid={!phoneValid}
            aria-describedby="phone-hint"
            onChange={(e) => setPhone(e.target.value.replace(/\s/g, ""))}
          />
          <span id="phone-hint" className={`mt-1.5 block text-xs ${phoneValid ? "text-ink-500" : "text-block"}`}>
            {t(phoneValid ? "send.phone_hint" : "send.phone_invalid")}
          </span>
        </label>
        <label>
          <span className="field-label">{t("send.email")}</span>
          <input className="field-input" type="email" value={email} onChange={(e) => setEmail(e.target.value.trim())} />
        </label>
        <label className="sm:col-span-2">
          <span className="field-label">{t("send.subject")}</span>
          <input className="field-input" value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
      </div>

      <label className="flex items-start gap-3 rounded-lg border border-rule bg-paper px-4 py-3">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-ink-950" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
        <span className="text-sm font-medium text-ink-950">{t("send.reviewed")}</span>
      </label>

      <div className="flex flex-wrap gap-2">
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
        {artifact?.data.pdf_base64 && (
          <a
            href={`data:application/pdf;base64,${artifact.data.pdf_base64}`}
            download={artifact.data.pdf_filename ?? `${caseId}-stage${stage}.pdf`}
            className="btn btn-quiet"
          >
            <Icon name="download" className="h-4 w-4" />
            {t("send.download_pdf")}
          </a>
        )}
      </div>
      <p className="flex items-center gap-2 text-xs text-ink-500">
        <Icon name="lock" className="h-3.5 w-3.5" />
        {t("send.disclaimer")}
      </p>
    </div>
  );
}
