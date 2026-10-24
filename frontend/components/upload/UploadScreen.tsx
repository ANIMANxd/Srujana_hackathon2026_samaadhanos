"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";
import { saveUploaded } from "@/lib/caseStore";
import {
  extractEvidence,
  FIELD_KEYS,
  REQUIRED_FIELDS,
  sampleExtraction,
  type ExtractedField,
  type Extraction,
  type FieldKey,
} from "@/lib/extraction";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { configEntry, useConfig } from "@/lib/useConfig";
import type { Activity, CaseRequest, EnterpriseClass } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^\d+(\.\d{1,2})?$/;
const PCT = /^\d+(\.\d{1,4})?$/;

const FIELD_LABEL: Record<FieldKey, MessageKey> = {
  invoice_number: "upload.field.invoice_number",
  invoice_date: "upload.field.invoice_date",
  amount: "upload.field.amount",
  supplier_gstin: "upload.field.supplier_gstin",
  buyer_gstin: "upload.field.buyer_gstin",
  buyer_name: "upload.field.buyer_name",
  delivery_date: "upload.field.delivery_date",
  po_reference: "upload.field.po_reference",
};

const FIELD_PATTERN: Partial<Record<FieldKey, RegExp>> = {
  invoice_date: DATE,
  delivery_date: DATE,
  amount: AMOUNT,
};

const CLASSES: EnterpriseClass[] = ["MICRO", "SMALL", "MEDIUM", "UNKNOWN"];
const ACTIVITIES: Activity[] = ["MANUFACTURING", "SERVICES", "TRADING"];

/** UI default for the buyer's cost of capital (architecture §8.2: "default from UI"). Editable. */
const DEFAULT_COC = "12.00";

function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type TaxPreset = { id: string; label: string; tax_rate_pct: string };

function taxPresets(value: unknown): TaxPreset[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((p) =>
    typeof p === "object" && p !== null && typeof (p as TaxPreset).tax_rate_pct === "string"
      ? [{ id: String((p as TaxPreset).id), label: String((p as TaxPreset).label), tax_rate_pct: (p as TaxPreset).tax_rate_pct }]
      : [],
  );
}

function fieldValid(key: FieldKey, f: ExtractedField): boolean {
  const v = f.value ?? "";
  if (v === "") return !REQUIRED_FIELDS.includes(key);
  const p = FIELD_PATTERN[key];
  return p ? p.test(v) : true;
}

function Review({ extraction, onCancel }: { extraction: Extraction; onCancel: () => void }) {
  const { t } = useT();
  const router = useRouter();
  const href = useHref();
  const cfg = useConfig();
  const presets = taxPresets(configEntry(cfg.config, "tax_presets")?.value);

  const [fields, setFields] = useState(extraction.fields);
  const [selected, setSelected] = useState<FieldKey>(FIELD_KEYS.find((k) => extraction.fields[k].method === "missing") ?? "invoice_date");
  const [supplierName, setSupplierName] = useState(extraction.supplier_name ?? "");
  const [klass, setKlass] = useState<EnterpriseClass>("UNKNOWN");
  const [activity, setActivity] = useState<Activity>("MANUFACTURING");
  const [nic, setNic] = useState("");
  const [udyamDate, setUdyamDate] = useState("");
  const [creditDays, setCreditDays] = useState("");
  const [calcDate, setCalcDate] = useState(todayLocal());
  const [taxPick, setTaxPick] = useState<string>("");
  const [taxManual, setTaxManual] = useState("");
  const [coc, setCoc] = useState(DEFAULT_COC);
  const [hasProof, setHasProof] = useState(false);

  const tax = taxPick && taxPick !== "manual" ? presets.find((p) => p.id === taxPick)?.tax_rate_pct ?? "" : taxManual;

  const fieldsOk = FIELD_KEYS.every((k) => fieldValid(k, fields[k]));
  const detailsOk =
    supplierName.trim() !== "" &&
    (udyamDate === "" || DATE.test(udyamDate)) &&
    (creditDays === "" || /^\d+$/.test(creditDays)) &&
    DATE.test(calcDate) &&
    PCT.test(tax) &&
    PCT.test(coc);
  const canApprove = fieldsOk && detailsOk;

  function setField(key: FieldKey, value: string) {
    setFields((prev) => ({
      ...prev,
      [key]: { ...prev[key], value: value === "" ? null : value, method: value === "" ? "missing" : prev[key].method === "missing" ? "manual" : prev[key].method },
    }));
  }

  function approve() {
    if (!canApprove) return;
    const v = (k: FieldKey) => fields[k].value;
    const id = `upload_${Date.now()}`;
    const request: CaseRequest = {
      contract_version: "1.0",
      case_id: id,
      supplier: {
        name: supplierName.trim(),
        udyam_number: null,
        enterprise_class: klass,
        activity,
        nic_codes: nic.split(",").map((s) => s.trim()).filter(Boolean),
        udyam_registration_date: udyamDate || null,
        investment_cr: null,
        turnover_cr: null,
      },
      buyer: { name: v("buyer_name") ?? "", gstin: v("buyer_gstin"), tax_rate_pct: tax, cost_of_capital_pct: coc },
      transaction: {
        contract_date: null,
        supply_date: v("delivery_date"),
        invoice_date: v("invoice_date") ?? "",
        delivery_date: v("delivery_date"),
        principal: v("amount") ?? "",
        written_credit_days: creditDays === "" ? null : Number(creditDays),
        calculation_date: calcDate,
        years_deferred: null,
      },
      objections: [],
      part_payments: [],
      acknowledgments: [],
      evidence: {
        items: [
          { kind: "INVOICE", present: true, ref: v("invoice_number") },
          { kind: "PO", present: Boolean(v("po_reference")), ref: v("po_reference") },
          { kind: "DELIVERY_PROOF", present: hasProof, ref: null },
          { kind: "WHATSAPP", present: false, ref: null },
          { kind: "UDYAM", present: false, ref: null },
          { kind: "GST_RETURN", present: false, ref: null },
        ],
      },
      config_overrides: null,
    };
    saveUploaded(request);
    router.push(href(`/case/${id}`));
  }

  const sel = fields[selected];

  return (
    <div className="flex flex-col gap-6">
      {extraction.placeholder && <Banner tone="warn" icon="warn" message="upload.unavailable" />}
      <header>
        <h2 className="font-display text-2xl font-semibold text-ink-950">{t("upload.review_title")}</h2>
        <p className="mt-1 text-ink-700">{t("upload.review_intro")}</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <ul className="panel flex flex-col divide-y divide-rule">
          {FIELD_KEYS.map((k) => {
            const f = fields[k];
            const valid = fieldValid(k, f);
            const required = REQUIRED_FIELDS.includes(k);
            const isSel = k === selected;
            const methodTone = f.method === "missing" ? "warn" : f.method === "llm" ? "info" : "ok";
            return (
              <li key={k} className={`flex flex-col gap-2 px-4 py-3 ${isSel ? "bg-saffron-100/40" : ""}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor={`f-${k}`} className="text-sm font-semibold text-ink-800">
                    {t(FIELD_LABEL[k])}
                    {required && <span className="ml-1 text-xs font-normal text-ink-500">({t("upload.required")})</span>}
                  </label>
                  <span className="flex items-center gap-2">
                    <StatusIcon size="sm" tone={methodTone} label={t(`upload.method.${f.method}`)} />
                    {f.method !== "missing" && f.method !== "manual" && (
                      <span className="text-xs text-ink-500">{t("upload.confidence", { n: Math.round(f.confidence * 100) })}</span>
                    )}
                  </span>
                </div>
                <input
                  id={`f-${k}`}
                  className="field-input num"
                  value={f.value ?? ""}
                  aria-invalid={!valid}
                  onFocus={() => setSelected(k)}
                  onChange={(e) => setField(k, e.target.value.trim())}
                  placeholder={FIELD_PATTERN[k] === DATE ? "YYYY-MM-DD" : undefined}
                />
              </li>
            );
          })}
        </ul>

        <aside aria-live="polite" className="panel flex flex-col gap-3 self-start p-5 lg:sticky lg:top-4">
          <h3 className="ledger-rule font-display text-lg font-semibold">{t("upload.source")}</h3>
          <p className="text-sm font-semibold text-ink-800">{t(FIELD_LABEL[selected])}</p>
          {sel.source_text ? (
            <>
              <blockquote className="rounded-sm border-l-4 border-saffron-500 bg-saffron-100/60 px-3 py-2 font-mono text-sm text-ink-900">
                <mark className="bg-transparent text-inherit">{sel.source_text}</mark>
              </blockquote>
              {sel.page !== null && <p className="text-xs text-ink-600">{t("upload.source_page", { n: sel.page })}</p>}
            </>
          ) : (
            <p className="text-sm text-warn">{t("upload.source_none")}</p>
          )}
          {extraction.placeholder && <PlaceholderBadge />}
        </aside>
      </div>

      <section aria-labelledby="details-title" className="panel flex flex-col gap-4 p-5">
        <h3 id="details-title" className="ledger-rule font-display text-lg font-semibold">{t("upload.details_title")}</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label>
            <span className="field-label">{t("upload.field.supplier_name")}</span>
            <input className="field-input" value={supplierName} aria-invalid={supplierName.trim() === ""} onChange={(e) => setSupplierName(e.target.value)} />
          </label>
          <label>
            <span className="field-label">{t("upload.field.enterprise_class")}</span>
            <select className="field-input" value={klass} onChange={(e) => setKlass(e.target.value as EnterpriseClass)}>
              {CLASSES.map((c) => <option key={c} value={c}>{t(`class.${c}`)}</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">{t("upload.field.activity")}</span>
            <select className="field-input" value={activity} onChange={(e) => setActivity(e.target.value as Activity)}>
              {ACTIVITIES.map((a) => <option key={a} value={a}>{t(`activity.${a}`)}</option>)}
            </select>
          </label>
          <label>
            <span className="field-label">{t("upload.field.nic_codes")}</span>
            <input className="field-input num" value={nic} onChange={(e) => setNic(e.target.value)} />
          </label>
          <label>
            <span className="field-label">{t("upload.field.udyam_date")}</span>
            <input className="field-input num" placeholder="YYYY-MM-DD" value={udyamDate} aria-invalid={udyamDate !== "" && !DATE.test(udyamDate)} onChange={(e) => setUdyamDate(e.target.value.trim())} />
          </label>
          <label>
            <span className="field-label">{t("upload.field.credit_days")}</span>
            <input className="field-input num" inputMode="numeric" value={creditDays} aria-invalid={creditDays !== "" && !/^\d+$/.test(creditDays)} onChange={(e) => setCreditDays(e.target.value.trim())} />
          </label>
          <label>
            <span className="field-label">{t("upload.field.calculation_date")}</span>
            <input className="field-input num" value={calcDate} aria-invalid={!DATE.test(calcDate)} onChange={(e) => setCalcDate(e.target.value.trim())} />
          </label>
          <label>
            <span className="field-label">{t("upload.field.buyer_tax")}</span>
            <select className="field-input" value={taxPick} onChange={(e) => setTaxPick(e.target.value)}>
              <option value="">—</option>
              {presets.map((p) => <option key={p.id} value={p.id}>{`${p.label} (${p.tax_rate_pct}%)`}</option>)}
              <option value="manual">{t("upload.tax_manual")}</option>
            </select>
            {(taxPick === "manual" || presets.length === 0) && (
              <input className="field-input num mt-2" inputMode="decimal" value={taxManual} aria-invalid={!PCT.test(taxManual)} onChange={(e) => setTaxManual(e.target.value.trim())} />
            )}
          </label>
          <label>
            <span className="field-label">{t("upload.field.coc")}</span>
            <input className="field-input num" inputMode="decimal" value={coc} aria-invalid={!PCT.test(coc)} onChange={(e) => setCoc(e.target.value.trim())} />
          </label>
        </div>
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-0.5 h-5 w-5" checked={hasProof} onChange={(e) => setHasProof(e.target.checked)} />
          <span className="text-ink-900">{t("upload.field.has_delivery_proof")}</span>
        </label>
      </section>

      <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center gap-3 border-t border-rule bg-paper/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-md sm:border">
        <button type="button" className="btn btn-primary" disabled={!canApprove} onClick={approve}>
          <Icon name="ok" className="h-4 w-4" />
          {t("upload.approve")}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onCancel}>
          {t("common.close")}
        </button>
        {!canApprove && <span className="text-sm text-ink-600">{t("upload.approve_disabled")}</span>}
      </div>
    </div>
  );
}

export function UploadScreen() {
  const { t } = useT();
  const input = useRef<HTMLInputElement>(null);
  const [extraction, setExtraction] = useState<Extraction | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handle(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError(t("upload.not_pdf"));
      return;
    }
    setReading(true);
    try {
      const e = await extractEvidence(file);
      setExtraction(e ?? sampleExtraction());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("state.error_title"));
    } finally {
      setReading(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    void handle(e.dataTransfer.files?.[0]);
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950">{t("upload.title")}</h1>
        <p className="mt-1 max-w-prose text-ink-700">{t("upload.intro")}</p>
      </header>

      {extraction ? (
        <Review extraction={extraction} onCancel={() => setExtraction(null)} />
      ) : (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center gap-4 rounded-lg border-2 border-dashed px-6 py-14 text-center ${
              dragOver ? "border-saffron-600 bg-saffron-100/50" : "border-rule-strong bg-paper-raised"
            }`}
          >
            <Icon name="upload" className="h-10 w-10 text-ink-500" />
            <p className="font-display text-xl font-semibold text-ink-900">{reading ? t("upload.reading") : t("upload.drop")}</p>
            <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" id="invoice-file" onChange={(e) => void handle(e.target.files?.[0])} />
            <div className="flex flex-wrap justify-center gap-3">
              <button type="button" className="btn btn-primary" disabled={reading} onClick={() => input.current?.click()}>
                {t("upload.choose")}
              </button>
              <button type="button" className="btn btn-secondary" disabled={reading} onClick={() => setExtraction(sampleExtraction())}>
                {t("upload.try_sample")}
              </button>
            </div>
          </div>
          {error && (
            <p role="alert" className="text-sm font-medium text-block">
              {error}
            </p>
          )}
        </>
      )}
    </div>
  );
}
