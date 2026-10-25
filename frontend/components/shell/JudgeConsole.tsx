"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listPresets } from "@/lib/api";
import { setEdited } from "@/lib/caseStore";
import { evidencePresent } from "@/lib/derive";
import { withDeliveryProof } from "@/lib/requestEdits";
import { count, date, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref, useUrlState } from "@/lib/params";
import { JUDGE_EVENT } from "@/lib/useConnection";
import type { Evaluation, EvaluationStatus } from "@/lib/useEvaluation";
import type {
  Activity,
  AppropriationMode,
  CaseRequest,
  CaseResponse,
  EnterpriseClass,
  PresetSummary,
  RateMode,
} from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { AMOUNT, DATE, DECIMAL, INT, TextField } from "../common/TextField";
import { useProductionMode } from "@/lib/useHealth";
import { Icon } from "../common/Icon";
import { JudgeDemoControls } from "./JudgeDemoControls";
import { EligibilityPill } from "../case/EligibilityPill";


const CLASSES: EnterpriseClass[] = ["MICRO", "SMALL", "MEDIUM", "UNKNOWN"];
const ACTIVITIES: Activity[] = ["MANUFACTURING", "SERVICES", "TRADING"];
const RATE_MODES: RateMode[] = ["FLOATING", "FROZEN_AT_APPOINTED_DAY"];
const APPROPRIATIONS: AppropriationMode[] = ["INTEREST_FIRST", "PRINCIPAL_FIRST"];
const SILPI = ["CONTRACT", "SUPPLY"] as const;

/** What the console needs from the open case (all of it from useEvaluation). */
export type JudgeCase = {
  caseId: string;
  request: CaseRequest;
  base: CaseRequest;
  response: CaseResponse | null;
  status: EvaluationStatus;
  refreshing: boolean;
  error: string | null;
  setRequest: (next: CaseRequest) => void;
  reset: () => void;
};

/** The console view of a case screen's evaluation, or null until its input is known. */
export function judgeCase(ev: Evaluation): JudgeCase | null {
  if (!ev.request || !ev.base) return null;
  return {
    caseId: ev.caseId,
    request: ev.request,
    base: ev.base,
    response: ev.response,
    status: ev.status,
    refreshing: ev.refreshing,
    error: ev.error,
    setRequest: ev.setRequest,
    reset: ev.reset,
  };
}

function Select<T extends string>({
  label,
  value,
  options,
  optionLabel,
  allowDefault,
  onChange,
}: {
  label: string;
  value: T | "";
  options: readonly T[];
  optionLabel: (v: T) => string;
  allowDefault: boolean;
  onChange: (v: T | null) => void;
}) {
  const { t } = useT();
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <select className="field-input" value={value} onChange={(e) => onChange((e.target.value || null) as T | null)}>
        {allowDefault && <option value="">{t("judge.f.default")}</option>}
        {options.map((o) => (
          <option key={o} value={o}>
            {optionLabel(o)}
          </option>
        ))}
      </select>
    </label>
  );
}

type T = ReturnType<typeof useT>["t"];

/** Plain-language "what changed" rows: one per editable field, base value → current value. */
function changes(base: CaseRequest, cur: CaseRequest, t: T): { label: string; from: string; to: string }[] {
  const none = t("judge.diff.none");
  const d = (v: string | null | undefined) => (v ? date(v) : none);
  const s = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? none : String(v));
  const yn = (v: boolean) => t(v ? "judge.diff.yes" : "judge.diff.no");
  const obj = (r: CaseRequest) => r.objections?.[0] ?? null;
  const ov = (r: CaseRequest) => r.config_overrides ?? {};
  const pays = (r: CaseRequest) => {
    const p = r.part_payments ?? [];
    return p.length === 0 ? none : p.map((x) => `${date(x.date)} ${money(x.amount)}`).join("; ");
  };
  const fields: [MessageKey, (r: CaseRequest) => string][] = [
    ["judge.f.invoice_date", (r) => d(r.transaction.invoice_date)],
    ["judge.f.delivery_date", (r) => d(r.transaction.delivery_date)],
    ["judge.f.delivery_proof", (r) => yn(evidencePresent(r, "DELIVERY_PROOF"))],
    ["judge.f.calculation_date", (r) => d(r.transaction.calculation_date)],
    ["judge.f.credit_days", (r) => s(r.transaction.written_credit_days)],
    ["judge.f.udyam_date", (r) => d(r.supplier.udyam_registration_date)],
    ["judge.f.class", (r) => t(`class.${r.supplier.enterprise_class}`)],
    ["judge.f.activity", (r) => t(`activity.${r.supplier.activity}`)],
    ["judge.f.investment", (r) => s(r.supplier.investment_cr)],
    ["judge.f.turnover", (r) => s(r.supplier.turnover_cr)],
    ["judge.f.objection_date", (r) => d(obj(r)?.raised_date)],
    ["judge.f.objection_written", (r) => (obj(r) ? yn(obj(r)?.is_written ?? false) : none)],
    ["judge.f.resolved_date", (r) => d(obj(r)?.resolved_date)],
    ["judge.f.bank_rate", (r) => s(ov(r).bank_rate_pct)],
    ["judge.f.rate_mode", (r) => { const m = ov(r).rate_mode; return m ? t(`mode.${m}`) : t("judge.f.default"); }],
    ["judge.f.appropriation", (r) => { const m = ov(r).appropriation_mode; return m ? t(`appropriation.${m}`) : t("judge.f.default"); }],
    ["judge.f.silpi", (r) => { const m = ov(r).silpi_test_date; return m ? t(`silpi.${m}`) : t("judge.f.default"); }],
    ["judge.f.payments", (r) => pays(r)],
    ["judge.f.cost_of_capital", (r) => s(r.buyer.cost_of_capital_pct)],
    ["judge.f.years_deferred", (r) => s(r.transaction.years_deferred)],
  ];
  return fields.flatMap(([key, get]) => {
    const from = get(base);
    const to = get(cur);
    return from === to ? [] : [{ label: t(key), from, to }];
  });
}

/** The engine's answer to the current edit, so the result is visible while the drawer is open. */
function LiveResult({ c }: { c: JudgeCase }) {
  const { t } = useT();
  const res = c.response;
  const days = res?.timeline?.days_overdue ?? null;
  return (
    <div aria-live="polite" className="flex flex-col gap-2 rounded-lg border border-rule bg-paper px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="eyebrow">{t("judge.result")}</span>
        {c.refreshing && <span className="text-xs text-ink-500">{t("judge.updating")}</span>}
      </div>
      {c.status === "needs_backend" ? (
        <p className="text-sm text-warn">{t("judge.needs_backend")}</p>
      ) : res ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <EligibilityPill status={res.jurisdiction.status} />
          <span className="num text-ink-950">{res.financials ? money(res.financials.total_claim) : t("judge.no_claim")}</span>
          {days !== null && days > 0 && <span className="num text-ink-600">{t("hero.overdue", { n: count(days) })}</span>}
        </div>
      ) : null}
      {c.error && <p className="text-xs text-block">{c.error}</p>}
    </div>
  );
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
  const setSupplier = (patch: Partial<CaseRequest["supplier"]>) => set({ ...r, supplier: { ...r.supplier, ...patch } });
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
  const setDeliveryProof = (held: boolean) => set(withDeliveryProof(r, held, c.base));
  const diff = changes(c.base, r, t);

  return (
    <div className="flex flex-col gap-6">
      <LiveResult c={c} />
      <p className="-mt-3 text-xs text-ink-500">{t("judge.edit_hint")}</p>

      <fieldset className="grid gap-3 sm:grid-cols-2">
        <legend className="eyebrow mb-3">{t("judge.group.dates")}</legend>
        <TextField label={t("judge.f.invoice_date")} value={tx.invoice_date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => setTx({ invoice_date: v })} />
        <TextField label={t("judge.f.delivery_date")} value={tx.delivery_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => setTx({ delivery_date: v || null })} />
        <TextField label={t("judge.f.calculation_date")} value={tx.calculation_date} pattern={DATE} errorKey="judge.invalid_date" allowEmpty={false} onCommit={(v) => setTx({ calculation_date: v })} />
        <TextField
          label={t("judge.f.credit_days")}
          value={tx.written_credit_days === null || tx.written_credit_days === undefined ? "" : String(tx.written_credit_days)}
          pattern={INT}
          errorKey="judge.invalid_int"
          allowEmpty
          onCommit={(v) => setTx({ written_credit_days: v === "" ? null : Number(v) })}
        />
        <label className="flex items-center gap-2 text-sm font-medium text-ink-800 sm:col-span-2">
          <input type="checkbox" className="h-4 w-4 accent-ink-950" checked={evidencePresent(r, "DELIVERY_PROOF")} onChange={(e) => setDeliveryProof(e.target.checked)} />
          {t("judge.f.delivery_proof")}
        </label>
      </fieldset>

      <fieldset className="grid gap-3 border-t border-rule pt-5 sm:grid-cols-2">
        <legend className="eyebrow mb-3 pt-5">{t("judge.group.supplier")}</legend>
        <TextField label={t("judge.f.udyam_date")} value={r.supplier.udyam_registration_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => setSupplier({ udyam_registration_date: v || null })} />
        <Select label={t("judge.f.class")} value={r.supplier.enterprise_class} options={CLASSES} optionLabel={(k) => t(`class.${k}`)} allowDefault={false} onChange={(v) => v && setSupplier({ enterprise_class: v })} />
        <Select label={t("judge.f.activity")} value={r.supplier.activity} options={ACTIVITIES} optionLabel={(k) => t(`activity.${k}`)} allowDefault={false} onChange={(v) => v && setSupplier({ activity: v })} />
        <TextField label={t("judge.f.investment")} value={r.supplier.investment_cr ?? ""} pattern={DECIMAL} errorKey="judge.invalid_crore" allowEmpty onCommit={(v) => setSupplier({ investment_cr: v || null })} />
        <TextField label={t("judge.f.turnover")} value={r.supplier.turnover_cr ?? ""} pattern={DECIMAL} errorKey="judge.invalid_crore" allowEmpty onCommit={(v) => setSupplier({ turnover_cr: v || null })} />
      </fieldset>

      <fieldset className="grid gap-3 border-t border-rule pt-5 sm:grid-cols-2">
        <legend className="eyebrow mb-3 pt-5">{t("judge.group.objection")}</legend>
        <TextField label={t("judge.f.objection_date")} value={obj?.raised_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => (v ? setObjection({ raised_date: v }) : setObjection(null))} />
        <TextField label={t("judge.f.resolved_date")} value={obj?.resolved_date ?? ""} pattern={DATE} errorKey="judge.invalid_date" allowEmpty onCommit={(v) => obj && setObjection({ resolved_date: v || null })} />
        <label className="flex items-center gap-2 text-sm font-medium text-ink-800">
          <input type="checkbox" className="h-4 w-4 accent-ink-950" checked={obj?.is_written ?? false} disabled={!obj} onChange={(e) => setObjection({ is_written: e.target.checked })} />
          {t("judge.f.objection_written")}
        </label>
      </fieldset>

      <fieldset className="grid gap-3 border-t border-rule pt-5 sm:grid-cols-2">
        <legend className="eyebrow mb-3 pt-5">{t("judge.group.rate")}</legend>
        <TextField label={t("judge.f.bank_rate")} value={overrides.bank_rate_pct ?? ""} pattern={DECIMAL} errorKey="judge.invalid_pct" allowEmpty onCommit={(v) => setOverrides({ bank_rate_pct: v || null })} />
        <Select label={t("judge.f.rate_mode")} value={overrides.rate_mode ?? ""} options={RATE_MODES} optionLabel={(k) => t(`mode.${k}`)} allowDefault onChange={(v) => setOverrides({ rate_mode: v })} />
        <Select label={t("judge.f.appropriation")} value={overrides.appropriation_mode ?? ""} options={APPROPRIATIONS} optionLabel={(k) => t(`appropriation.${k}`)} allowDefault onChange={(v) => setOverrides({ appropriation_mode: v })} />
        <Select label={t("judge.f.silpi")} value={overrides.silpi_test_date ?? ""} options={SILPI} optionLabel={(k) => t(`silpi.${k}`)} allowDefault onChange={(v) => setOverrides({ silpi_test_date: v })} />
      </fieldset>

      <fieldset className="flex flex-col gap-3 border-t border-rule pt-5">
        <legend className="eyebrow mb-3 pt-5">{t("judge.f.payments")}</legend>
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

      <div className="flex flex-col gap-3 border-t border-rule pt-5">
        <div className="flex items-center justify-between gap-3">
          <p className="section-title">{t("judge.changed")}</p>
          <button type="button" className="btn btn-secondary min-h-8 px-3 text-xs" onClick={c.reset} disabled={diff.length === 0}>
            {t("judge.reset")}
          </button>
        </div>
        {diff.length === 0 ? (
          <p className="text-sm text-ink-500">{t("judge.unchanged")}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
            {diff.map((d) => (
              <li key={d.label} className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[11rem_1fr]">
                <span className="text-ink-600">{d.label}</span>
                <span className="num flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-ink-500 line-through decoration-ink-300">{d.from}</span>
                  <Icon name="arrow-right" className="h-3 w-3 text-ink-300" />
                  <span className="text-ink-950">{d.to}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/**
 * Judge console slide-over (frontend-structure §1): Ctrl+J, the top-bar button,
 * or ?judge=1. Presets to load, and a live edit form when a case is open.
 */
export function JudgeConsole({ current }: { current?: JudgeCase | null }) {
  const { t } = useT();
  const href = useHref();
  const { judge, demo } = useUrlState();
  // Demo mode hides the rehearsal console by default; ?judge=1 is the explicit escape hatch.
  const production = useProductionMode();
  const enabled = (!demo || judge) && !production;
  const [open, setOpen] = useState(judge);
  const [presets, setPresets] = useState<PresetSummary[]>([]);

  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !open) return;
    let alive = true;
    listPresets()
      .then((p) => alive && setPresets(p.data))
      .catch(() => alive && setPresets([]));
    return () => {
      alive = false;
    };
  }, [enabled, open]);

  /** Loading a preset always shows the preset itself: any earlier edits to it are dropped. */
  function load(id: string) {
    if (current && current.caseId === id) current.reset();
    else setEdited(id, null);
    setOpen(false);
  }

  if (!enabled) return null;

  return (
    <Drawer open={open} onClose={() => setOpen(false)} title={t("judge.title")} width="lg">
      <div className="flex flex-col gap-8">
        <p className="-mt-2 text-xs text-ink-500">{t("judge.hint")}</p>
        <section aria-labelledby="judge-presets">
          <h3 id="judge-presets" className="section-title">{t("judge.presets")}</h3>
          <ul className="mt-3 flex flex-col divide-y divide-rule rounded-lg border border-rule">
            {presets.map((p) => {
              const isOpen = current?.caseId === p.id;
              return (
                <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="text-sm text-ink-900">{p.title}</span>
                  <Link
                    href={href(`/case/${p.id}`)}
                    className={`btn min-h-8 shrink-0 px-3 text-xs ${isOpen ? "btn-primary" : "btn-secondary"}`}
                    aria-current={isOpen ? "page" : undefined}
                    onClick={() => load(p.id)}
                  >
                    {t("judge.load")}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
        <section aria-labelledby="judge-demo">
          <h3 id="judge-demo" className="section-title">{t("judge.demo.title")}</h3>
          <div className="mt-3">
            <JudgeDemoControls caseId={current?.caseId ?? null} open={open} />
          </div>
        </section>
        <section aria-labelledby="judge-edit">
          <h3 id="judge-edit" className="section-title">{t("judge.edit")}</h3>
          <div className="mt-3">{current ? <EditForm c={current} /> : <p className="text-sm text-ink-500">{t("judge.no_case")}</p>}</div>
        </section>
      </div>
    </Drawer>
  );
}
