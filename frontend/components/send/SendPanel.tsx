"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ApiError, generateArtifact, type SourcedArtifact } from "@/lib/api";
import { logPrepared, useSendLog } from "@/lib/caseStore";
import { evidencePresent, stageLock } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { ArtifactKind, CaseRequest, CaseResponse, Stage } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Markdown } from "../common/Markdown";
import { StatusIcon } from "../common/StatusIcon";
import { toPlainMessage } from "@/lib/outgoing";
import { financingLocksRecovery } from "@/lib/recoveryFlow";
import type { TrackView } from "@/lib/useTrack";
import { LockedNotice } from "../early/LockedNotice";
import { Banner } from "../shell/Banners";
import { RecoveryActions } from "./RecoveryActions";
import { SendButtons, isPhoneValid } from "./SendButtons";

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Stage 1 asks for receipt first when there is no delivery proof (B8). */
export function kindFor(stage: Stage, req: CaseRequest, res: CaseResponse): ArtifactKind {
  if (stage === 2) return "STAGE2_CFO_MEMO";
  if (stage === 3) return "STAGE3_SETTLEMENT_TERMSHEET";
  if (stage === 4) return "STAGE4_EVIDENCE_PACK";
  const noProof = !evidencePresent(req, "DELIVERY_PROOF") || res.timeline?.objection_status === "NO_DELIVERY_PROOF";
  return noProof ? "STAGE1_ACCEPTANCE_NOTE" : "STAGE1_BALANCE_CONFIRMATION";
}

type Draft =
  | { state: "loading" }
  | { state: "ready"; artifact: SourcedArtifact; text: string; base: string }
  | { state: "needs_backend" }
  | { state: "error"; message: string };

/**
 * The engine drafts a stage; the owner previews it, edits it if they like, and
 * opens their own app. Nothing auto-sends: copy, WhatsApp, email and print stay
 * disabled until "I have reviewed this draft" is ticked. Stage 4 is a checklist
 * and evidence bundle, so it has no WhatsApp or email actions.
 */
export function SendPanel({
  caseId,
  stage,
  request,
  response,
  offlineId,
  tracking = null,
}: {
  caseId: string;
  stage: Stage;
  request: CaseRequest;
  response: CaseResponse;
  offlineId: string | null;
  /** Stored cases only: records prepared / sent against the recovery track. */
  tracking?: TrackView | null;
}) {
  const { t, tWarning } = useT();
  const href = useHref();
  const kind = kindFor(stage, request, response);
  const isPack = stage === 4;
  const [draft, setDraft] = useState<Draft>({ state: "loading" });
  const [mode, setMode] = useState<"preview" | "edit">("preview");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [subjectEdit, setSubject] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [usedNow, setUsedNow] = useState(false);
  const sendLog = useSendLog(caseId);

  useEffect(() => {
    let alive = true;
    generateArtifact(kind, request, offlineId)
      .then((a) => {
        if (!alive) return;
        if (!a) {
          setDraft({ state: "needs_backend" });
          return;
        }
        // The message the owner sends is plain text without the owner-only banner, notes and footer;
        // the evidence pack (stage 4) is a checklist for the owner and stays as written.
        const base = kind === "STAGE4_EVIDENCE_PACK" ? a.data.markdown : toPlainMessage(a.data.markdown);
        setDraft({ state: "ready", artifact: a, text: base, base });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setDraft({ state: "error", message: e instanceof ApiError ? e.message : t("state.error_title") });
      });
    return () => {
      alive = false;
    };
  }, [kind, request, offlineId, t]);

  // Print fallback: mark the body so print CSS shows only the portal'd draft.
  useEffect(() => {
    if (!printing) return;
    document.body.dataset.print = "draft";
    const done = () => setPrinting(false);
    window.addEventListener("afterprint", done);
    const timer = setTimeout(() => window.print(), 60);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("afterprint", done);
      delete document.body.dataset.print;
    };
  }, [printing]);

  const locked = stageLock(response, stage) !== null;
  const subject = subjectEdit ?? t("send.subject_default", { title: t(`stage.${stage}.title`), supplier: request.supplier.name });
  const text = draft.state === "ready" ? draft.text : "";
  const edited = draft.state === "ready" && draft.text !== draft.base;
  const phoneValid = isPhoneValid(phone);
  const canAct = reviewed && text.trim().length > 0 && !locked;
  const used = usedNow || sendLog.some((e) => e.stage === stage);
  const prepared = () => {
    logPrepared(caseId, stage, todayLocal());
    setUsedNow(true);
  };

  if (tracking && financingLocksRecovery(tracking.track)) return <LockedNotice dueDate={response.timeline?.due_date ?? null} />;
  if (locked) return <Banner tone="block" icon="lock" message="send.blocked" />;

  const artifact = draft.state === "ready" ? draft.artifact : null;
  const pdf = artifact?.data.pdf_base64 ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <StatusIcon size="sm" tone="info" icon="doc" label={t("badge.draft")} />
        <p className="text-sm text-ink-600">{t(`stage.${stage}.purpose`)}</p>
      </div>

      {isPack && (
        <p className="flex items-start gap-2 rounded-lg border border-warn/25 bg-warn-wash px-3.5 py-2 text-sm text-warn">
          <Icon name="warn" className="mt-0.5 h-4 w-4 shrink-0" />
          {t("esc.stage4.note")}
        </p>
      )}
      {artifact?.source === "offline" && <Banner tone="info" icon="info" message="send.sample_draft" />}
      {draft.state === "needs_backend" && <Banner tone="warn" icon="lock" message="send.needs_backend" />}
      {draft.state === "error" && (
        <div role="alert" className="rounded-lg border border-block/25 bg-block-wash px-3.5 py-2 text-sm text-block">
          {draft.message}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <span className="field-label mb-0">{t("send.draft_label")}</span>
          <div role="radiogroup" aria-label={t("send.draft_label")} className="inline-flex rounded-lg border border-rule bg-paper-sunk p-0.5 text-xs">
            {(["preview", "edit"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
                  mode === m ? "bg-paper-raised text-ink-950 shadow-[0_1px_2px_rgb(13_13_12/0.08)]" : "text-ink-500 hover:text-ink-950"
                }`}
              >
                {t(m === "preview" ? "esc.preview" : "esc.edit")}
              </button>
            ))}
          </div>
        </div>
        {draft.state === "loading" ? (
          <div className="flex h-72 items-center justify-center rounded-lg border border-rule bg-paper text-sm text-ink-500" aria-busy="true">
            {t("send.loading")}
          </div>
        ) : mode === "preview" ? (
          <div className="max-h-[32rem] overflow-y-auto rounded-lg border border-rule bg-paper-raised p-5">
            {text ? isPack ? <Markdown source={text} /> : <p className="whitespace-pre-wrap text-[0.9375rem] leading-relaxed text-ink-900">{text}</p> : null}
          </div>
        ) : (
          <textarea
            className="field-input min-h-80 font-mono text-[0.8125rem] leading-relaxed"
            value={text}
            disabled={draft.state !== "ready"}
            onChange={(e) => draft.state === "ready" && setDraft({ ...draft, text: e.target.value })}
          />
        )}
      </div>

      {artifact && (artifact.data.warnings ?? []).length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs font-medium text-ink-600 hover:text-ink-950">{t("send.notes")}</summary>
          <ul className="mt-2 flex flex-col gap-1.5 text-ink-700">
            {(artifact.data.warnings ?? []).map((w, i) => (
              <li key={`${w.code}-${i}`}>{tWarning(w.code, w.text)}</li>
            ))}
          </ul>
        </details>
      )}

      {!isPack && (
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
      )}

      <label className="flex items-start gap-3 rounded-lg border border-rule bg-paper px-4 py-3">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-ink-950" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
        <span className="text-sm font-medium text-ink-950">{t("send.reviewed")}</span>
      </label>

      <div className="flex flex-wrap gap-2">
        <SendButtons
          text={text}
          subject={subject}
          phone={phone}
          email={email}
          enabled={canAct}
          channels={!isPack}
          copyPrimary={isPack}
          onPrepared={prepared}
        />
        {pdf ? (
          <a
            href={`data:application/pdf;base64,${pdf}`}
            download={artifact?.data.pdf_filename ?? `${caseId}-stage${stage}.pdf`}
            className="btn btn-quiet"
          >
            <Icon name="download" className="h-4 w-4" />
            {t("send.download_pdf")}
          </a>
        ) : (
          <button
            type="button"
            className="btn btn-quiet"
            disabled={!canAct}
            title={t("esc.print_hint")}
            onClick={() => {
              prepared();
              setPrinting(true);
            }}
          >
            <Icon name="download" className="h-4 w-4" />
            {t("esc.print")}
          </button>
        )}
        {isPack && (
          <Link href={href(`/case/${caseId}/pack`)} className="btn btn-quiet">
            {t("esc.stage4.full_pack")}
            <Icon name="arrow-right" className="h-4 w-4" />
          </Link>
        )}
      </div>
      {pdf && edited && <p className="text-xs text-ink-500">{t("esc.edited_pdf_note")}</p>}
      <p className="flex items-center gap-2 text-xs text-ink-500">
        <Icon name="lock" className="h-3.5 w-3.5" />
        {t("send.disclaimer")}
      </p>

      {tracking?.caseDetail && !isPack && <RecoveryActions caseId={caseId} stage={stage} tracking={tracking} used={used} />}

      {printing &&
        createPortal(
          <div className="print-draft">
            <p className="print-draft-banner">{t("pack.print_banner")}</p>
            {isPack ? <Markdown source={text} /> : <p className="whitespace-pre-wrap">{text}</p>}
          </div>,
          document.body,
        )}
    </div>
  );
}
