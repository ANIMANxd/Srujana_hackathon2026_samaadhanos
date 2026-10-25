"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listPresets } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref, useUrlState } from "@/lib/params";
import { JUDGE_EVENT } from "@/lib/useConnection";
import type {
  Activity,
  AppropriationMode,
  CaseRequest,
  EnterpriseClass,
  PresetSummary,
  RateMode,
} from "@/lib/types";
import { Drawer } from "../common/Drawer";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^\d+(\.\d{1,2})?$/;
const INT = /^\d+$/;
const PCT = /^\d+(\.\d{1,4})?$/;

const CLASSES: EnterpriseClass[] = ["MICRO", "SMALL", "MEDIUM", "UNKNOWN"];
const ACTIVITIES: Activity[] = ["MANUFACTURING", "SERVICES", "TRADING"];
const RATE_MODES: RateMode[] = ["FLOATING", "FROZEN_AT_APPOINTED_DAY"];
const APPROPRIATIONS: AppropriationMode[] = ["INTEREST_FIRST", "PRINCIPAL_FIRST"];

export type JudgeCase = {
  request: CaseRequest;
  base: CaseRequest;
  setRequest: (next: CaseRequest) => void;
  reset: () => void;
};

/** Field that keeps its own draft text and only commits valid values. */
function TextField({
  label,
  value,
  pattern,
  errorKey,
  allowEmpty,
  onCommit,
}: {
  label: string;
  value: string;
  pattern: RegExp;
  errorKey: MessageKey;
  allowEmpty: boolean;
  onCommit: (v: string) => void;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  if (synced !== value) {
    setSynced(value);
    setDraft(value);
  }
  const valid = (allowEmpty && draft === "") || pattern.test(draft);
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input
        className="field-input num"
        value={draft}
        aria-invalid={!valid}
        onChange={(e) => {
          const v = e.target.value.trim();
          setDraft(v);
          if ((allowEmpty && v === "") || pattern.test(v)) onCommit(v);
        }}
      />
      {!valid && <span className="mt-1 block text-xs text-block">{t(errorKey)}</span>}
    </label>
  );
}

function diffList(base: CaseRequest, cur: CaseRequest): string[] {
  const out: string[] = [];
  const walk = (a: unknown, b: unknown, path: string) => {
    if (JSON.stringify(a) === JSON.stringify(b)) return;
    if (a && b && typeof a === "object" && typeof b === "object" && !Array.isArray(a) && !Array.isArray(b)) {
      const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
      keys.forEach((k) => walk((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k], path ? `${path}.${k}` : k));
      return;
    }
    out.push(`${path}: ${JSON.stringify(a ?? null)} → ${JSON.stringify(b ?? null)}`);
  };
  walk(base, cur, "");
  return out;
}

function EditForm({ c }: { c: JudgeCase }) {
  const { t } = useT();
  const r = c.request;
  const tx = r.transaction;
  const obj = r.objections?.[0] ?? null;
  const overrides = r.config_overrides ?? {};
  const payments = r.part_payments ?? [];
  const set = (next: CaseRequest) => c.setRequest(next);
  const setTx = (patch: Partial<CaseRequest["transaction"]>) => set({ ...r, transaction: { ...tx, ...patch } });
  const setOverrides = (patch: NonNullable<CaseRequest["config_overrides"]>) => {
    const merged = { ...overrides, ...patch };
    const cleaned = Object.fromEntries(Object.entries(merged).filter(([, v]) => v !== null && v !== undefined));
    set({ ...r, config_overrides: Object.keys(cleaned).length ? cleaned : null });
  };
  const setObjection = (patch: Partial<NonNullable<typeof obj>> | null) => {
    if (patch === null) return set({ ...r, objections: [] });
    const base = obj ?? { raised_date: tx.delivery_date ?? tx.invoice_date, is_written: true, description: null, resolved_date: null };
    set({ ...r, objections: [{ ...base, ...patch }, ...(r.objections ?? []).slice(1)] });
  };
  const changes = diffList(c.base, r);

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-600">{t("judge.edit_hint")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label={t("judge.f.invoice_date")} value={tx.invoice_date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => setTx({ invoice_date: v })} />
        <TextField label={t("judge.f.delivery_date")} value={tx.delivery_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => setTx({ delivery_date: v || null })} />
        <TextField label={t("judge.f.calculation_date")} value={tx.calculation_date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => setTx({ calculation_date: v })} />
        <TextField label={t("judge.f.credit_days")} value={tx.written_credit_days === null || tx.written_credit_days === undefined ? "" : String(tx.written_credit_days)} pattern={INT} errorKey="judge.invalid_int" allowEmpty onCommit={(v) => setTx({ written_credit_days: v === "" ? null : Number(v) })} />
        <TextField label={t("judge.f.udyam_date")} value={r.supplier.udyam_registration_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => set({ ...r, supplier: { ...r.supplier, udyam_registration_date: v || null } })} />
        <label className="block">
          <span className="field-label">{t("judge.f.class")}</span>
          <select className="field-input" value={r.supplier.enterprise_class} onChange={(e) => set({ ...r, supplier: { ...r.supplier, enterprise_class: e.target.value as EnterpriseClass } })}>
            {CLASSES.map((k) => <option key={k} value={k}>{t(`class.${k}`)}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="field-label">{t("judge.f.activity")}</span>
          <select className="field-input" value={r.supplier.activity} onChange={(e) => set({ ...r, supplier: { ...r.supplier, activity: e.target.value as Activity } })}>
            {ACTIVITIES.map((k) => <option key={k} value={k}>{t(`activity.${k}`)}</option>)}
          </select>
        </label>
      </div>

      <fieldset className="grid gap-3 border-t border-rule pt-4 sm:grid-cols-2">
        <TextField label={t("judge.f.objection_date")} value={obj?.raised_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => (v ? setObjection({ raised_date: v }) : setObjection(null))} />
        <TextField label={t("judge.f.resolved_date")} value={obj?.resolved_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => obj && setObjection({ resolved_date: v || null })} />
        <label className="flex items-center gap-2 text-sm font-medium text-ink-800">
          <input type="checkbox" className="h-5 w-5" checked={obj?.is_written ?? false} disabled={!obj} onChange={(e) => setObjection({ is_written: e.target.checked })} />
          {t("judge.f.objection_written")}
        </label>
      </fieldset>

      <fieldset className="grid gap-3 border-t border-rule pt-4 sm:grid-cols-3">
        <TextField label={t("judge.f.bank_rate")} value={overrides.bank_rate_pct ?? ""} pattern={PCT} errorKey="judge.invalid_amount" allowEmpty onCommit={(v) => setOverrides({ bank_rate_pct: v || null })} />
        <label className="block">
          <span className="field-label">{t("judge.f.rate_mode")}</span>
          <select className="field-input" value={overrides.rate_mode ?? ""} onChange={(e) => setOverrides({ rate_mode: (e.target.value || null) as RateMode | null })}>
            <option value="">{t("judge.f.default")}</option>
            {RATE_MODES.map((k) => <option key={k} value={k}>{t(`mode.${k}`)}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="field-label">{t("judge.f.appropriation")}</span>
          <select className="field-input" value={overrides.appropriation_mode ?? ""} onChange={(e) => setOverrides({ appropriation_mode: (e.target.value || null) as AppropriationMode | null })}>
            <option value="">{t("judge.f.default")}</option>
            {APPROPRIATIONS.map((k) => <option key={k} value={k}>{t(`appropriation.${k}`)}</option>)}
          </select>
        </label>
      </fieldset>

      <fieldset className="flex flex-col gap-3 border-t border-rule pt-4">
        <legend className="mb-1 text-sm font-semibold text-ink-800">{t("judge.f.payments")}</legend>
        {payments.map((p, i) => (
          <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <TextField label={t("judge.f.payment_date")} value={p.date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => set({ ...r, part_payments: payments.map((q, j) => (j === i ? { ...q, date: v } : q)) })} />
            <TextField label={t("judge.f.payment_amount")} value={p.amount} pattern={AMOUNT} errorKey="judge.invalid_amount" allowEmpty={false} onCommit={(v) => set({ ...r, part_payments: payments.map((q, j) => (j === i ? { ...q, amount: v } : q)) })} />
            <button type="button" className="btn btn-secondary" onClick={() => set({ ...r, part_payments: payments.filter((_, j) => j !== i) })}>
              {t("judge.remove")}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-secondary self-start"
          onClick={() => set({ ...r, part_payments: [...payments, { date: tx.calculation_date, amount: "0.00", reference: null }] })}
        >
          {t("judge.add_payment")}
        </button>
      </fieldset>

      <div className="flex flex-col gap-2 border-t border-rule pt-4">
        <p className="text-sm font-semibold text-ink-800">{t("judge.changed")}</p>
        {changes.length === 0 ? (
          <p className="text-sm text-ink-600">{t("judge.unchanged")}</p>
        ) : (
          <ul className="flex flex-col gap-0.5 font-mono text-xs text-ink-800">
            {changes.map((d) => <li key={d} className="break-all">{d}</li>)}
          </ul>
        )}
        <button type="button" className="btn btn-secondary self-start" onClick={c.reset} disabled={changes.length === 0}>
          {t("judge.reset")}
        </button>
      </div>
    </div>
  );
}

/**
 * Hidden judge console (frontend-structure §1): Ctrl+J or ?judge=1.
 * Presets to load, and a live edit form when a case is open.
 */
export function JudgeConsole({ current }: { current?: JudgeCase | null }) {
  const { t } = useT();
  const href = useHref();
  const { judge } = useUrlState();
  const [open, setOpen] = useState(judge);
  const [presets, setPresets] = useState<PresetSummary[]>([]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    const onToggle = () => setOpen((o) => !o);
    window.addEventListener("keydown", onKey);
    window.addEventListener(JUDGE_EVENT, onToggle);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(JUDGE_EVENT, onToggle);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    listPresets()
      .then((p) => alive && setPresets(p.data))
      .catch(() => alive && setPresets([]));
    return () => {
      alive = false;
    };
  }, [open]);

  return (
    <Drawer open={open} onClose={() => setOpen(false)} title={t("judge.title")} width="lg">
      <div className="flex flex-col gap-6">
        <p className="text-sm text-ink-600">{t("judge.hint")}</p>
        <section>
          <h3 className="section-title">{t("judge.presets")}</h3>
          <ul className="mt-3 flex flex-col gap-2">
            {presets.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3">
                <span className="text-sm text-ink-900">{p.title}</span>
                <Link href={href(`/case/${p.id}`)} className="btn btn-secondary min-h-9 px-3 text-sm" onClick={() => setOpen(false)}>
                  {t("judge.load")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h3 className="section-title">{t("judge.edit")}</h3>
          <div className="mt-3">{current ? <EditForm c={current} /> : <p className="text-sm text-ink-600">{t("judge.no_case")}</p>}</div>
        </section>
      </div>
    </Drawer>
  );
}
