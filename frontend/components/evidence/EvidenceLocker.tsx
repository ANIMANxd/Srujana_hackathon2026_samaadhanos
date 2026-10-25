"use client";

import { useT } from "@/lib/i18n";
import { EVIDENCE_ORDER, withDeliveryProof, withEvidence } from "@/lib/requestEdits";
import type { CaseRequest, CaseResponse, Objection } from "@/lib/types";
import { DATE, TextField } from "../common/TextField";
import { ChatLines } from "./ChatLines";
import { Meaning } from "./Meaning";

const REF = /^.{0,80}$/;
const NOTE = /^.{0,200}$/;

/**
 * Manual evidence entry (MVP): which documents are held, the delivery date and
 * the buyer's objections. Every change goes back to the engine through the
 * case's useEvaluation, exactly like a judge-console edit.
 */
export function EvidenceLocker({
  request,
  base,
  response,
  onChange,
}: {
  request: CaseRequest;
  base: CaseRequest;
  response: CaseResponse;
  onChange: (next: CaseRequest) => void;
}) {
  const { t } = useT();
  const r = request;
  const objections = r.objections ?? [];
  const missing = response.evidence_readiness.missing;
  const item = (kind: (typeof EVIDENCE_ORDER)[number]) => r.evidence.items.find((i) => i.kind === kind);

  const setObjection = (i: number, patch: Partial<Objection>) =>
    onChange({ ...r, objections: objections.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  const addObjection = () =>
    onChange({
      ...r,
      objections: [
        ...objections,
        { raised_date: r.transaction.delivery_date ?? r.transaction.invoice_date, is_written: true, description: null, resolved_date: null },
      ],
    });

  return (
    <section aria-labelledby="locker-title" className="panel flex flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h2 id="locker-title" className="section-title">{t("locker.title")}</h2>
        <p className="text-sm text-ink-600">{t("locker.intro")}</p>
      </div>

      <ul className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
        {EVIDENCE_ORDER.map((kind) => {
          const it = item(kind);
          const held = it?.present ?? false;
          return (
            <li key={kind} className="grid items-center gap-3 px-4 py-3 sm:grid-cols-[1fr_12rem]">
              <label className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-ink-950"
                  checked={held}
                  onChange={(e) =>
                    onChange(kind === "DELIVERY_PROOF" ? withDeliveryProof(r, e.target.checked, base) : withEvidence(r, kind, { present: e.target.checked }))
                  }
                />
                <span className={held ? "text-ink-950" : "text-ink-600"}>{t(`evidence.${kind}`)}</span>
                {!held && missing.includes(kind) && (
                  <span className="rounded-full bg-warn-wash px-2 py-0.5 text-xs font-medium text-warn">{t("pack.missing")}</span>
                )}
              </label>
              {held && (
                <TextField
                  label={t("locker.ref")}
                  value={it?.ref ?? ""}
                  pattern={REF}
                  errorKey="locker.ref_too_long"
                  allowEmpty
                  onCommit={(v) => onChange(withEvidence(r, kind, { ref: v || null }))}
                />
              )}
            </li>
          );
        })}
      </ul>

      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label={t("judge.f.delivery_date")}
          value={r.transaction.delivery_date ?? ""}
          pattern={DATE}
          errorKey="judge.invalid_date"
          allowEmpty
          onCommit={(v) => onChange({ ...r, transaction: { ...r.transaction, delivery_date: v || null } })}
        />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-ink-950">{t("locker.objections")}</h3>
          <button type="button" className="btn btn-secondary min-h-8 px-3 text-xs" onClick={addObjection}>
            {t("locker.add_objection")}
          </button>
        </div>
        {objections.length === 0 ? (
          <p className="text-sm text-ink-500">{t("locker.no_objections")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {objections.map((o, i) => (
              <li key={i} className="flex flex-col gap-3 rounded-lg border border-rule p-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="eyebrow">{t("locker.objection_n", { n: i + 1 })}</span>
                  <button
                    type="button"
                    className="btn btn-quiet min-h-8 px-2 text-xs"
                    onClick={() => onChange({ ...r, objections: objections.filter((_, j) => j !== i) })}
                  >
                    {t("judge.remove")}
                  </button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <TextField label={t("judge.f.objection_date")} value={o.raised_date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => setObjection(i, { raised_date: v })} />
                  <TextField label={t("judge.f.resolved_date")} value={o.resolved_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => setObjection(i, { resolved_date: v || null })} />
                </div>
                <TextField
                  label={t("locker.objection.description")}
                  value={o.description ?? ""}
                  pattern={NOTE}
                  errorKey="locker.note_too_long"
                  allowEmpty
                  mono={false}
                  onCommit={(v) => setObjection(i, { description: v || null })}
                />
                <label className="flex items-center gap-2 text-sm text-ink-800">
                  <input type="checkbox" className="h-4 w-4 accent-ink-950" checked={o.is_written} onChange={(e) => setObjection(i, { is_written: e.target.checked })} />
                  {t("judge.f.objection_written")}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-rule pt-5">
        <ChatLines />
      </div>

      <Meaning block="evidence" code={missing.length === 0 ? "ALL" : "MISSING"} />
    </section>
  );
}
