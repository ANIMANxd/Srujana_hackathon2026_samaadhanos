"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent } from "react";
import { ApiError, BackendUnreachable, extractEvidence } from "@/lib/api";
import { saveUploaded } from "@/lib/caseStore";
import { FIELD_KEYS, looksLikeText, REQUIRED_FIELDS, reviewFields, type FieldKey, type ReviewField } from "@/lib/extraction";
import { EXTRACTION_SAMPLES, type ExtractionSample } from "@/lib/fixtures";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { configEntry, useConfig } from "@/lib/useConfig";
import type { Activity, CaseRequest, EnterpriseClass, ExtractionResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";
import { JudgeConsole } from "../shell/JudgeConsole";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^\d+(\.\d{1,2})?$/;
const PCT = /^\d+(\.\d{1,4})?$/;
const INT = /^\d+$/;

const FIELD_LABEL: Record<FieldKey, MessageKey> = {
  invoice_number: "upload.field.invoice_number",
  invoice_date: "upload.field.invoice_date",
  amount: "upload.field.amount",
  supplier_gstin: "upload.field.supplier_gstin",
  buyer_gstin: "upload.field.buyer_gstin",
  buyer_name: "upload.field.buyer_name",
  delivery_date: "upload.field.delivery_date",
  po_reference: "upload.field.po_reference",
  written_credit_days: "upload.field.written_credit_days",
};

const FIELD_PATTERN: Partial<Record<FieldKey, RegExp>> = {
  invoice_date: DATE,
  delivery_date: DATE,
  amount: AMOUNT,
  written_credit_days: INT,
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

function fieldValid(key: FieldKey, f: ReviewField): boolean {
  const v = f.value ?? "";
  if (v === "") return !REQUIRED_FIELDS.includes(key);
  const p = FIELD_PATTERN[key];
  return p ? p.test(v) : true;
}

type Result = { response: ExtractionResponse; offlineSample: boolean };

function Review({ result, onCancel }: { result: Result; onCancel: () => void }) {
  const { t, tWarning } = useT();
  const router = useRouter();
  const href = useHref();
  const cfg = useConfig();
  const presets = taxPresets(configEntry(cfg.config, "tax_presets")?.value);
  const res = result.response;
  const isChat = res.kind === "WHATSAPP_EXPORT";

  const [fields, setFields] = useState(() => reviewFields(res));
  const [selected, setSelected] = useState<FieldKey>(() => FIELD_KEYS.find((k) => fields[k].method !== "missing") ?? "invoice_date");
  const [supplierName, setSupplierName] = useState(res.supplier_name ?? "");
  const [klass, setKlass] = useState<EnterpriseClass>("UNKNOWN");
  const [activity, setActivity] = useState<Activity>("MANUFACTURING");
  const [nic, setNic] = useState("");
  const [udyamDate, setUdyamDate] = useState("");
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
    DATE.test(calcDate) &&
    PCT.test(tax) &&
    PCT.test(coc);
  const canApprove = fieldsOk && detailsOk;

  function setField(key: FieldKey, value: string) {
    setFields((prev) => ({ ...prev, [key]: { ...prev[key], value: value === "" ? null : value, edited: true } }));
  }

  function approve() {
    if (!canApprove) return;
    const v = (k: FieldKey) => fields[k].value;
    const id = `upload_${Date.now()}`;
    const credit = v("written_credit_days");
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
        written_credit_days: credit === null ? null : Number(credit),
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
          { kind: "WHATSAPP", present: isChat, ref: null },
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
  const messages = res.messages ?? [];
  const notes = res.warnings ?? [];

  return (
    <div className="flex flex-col gap-6">
      {result.offlineSample && <Banner tone="info" icon="info" message="upload.offline_sample" />}

      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold tracking-[-0.015em] text-ink-950">{t("upload.review_title")}</h2>
          <StatusIcon size="sm" tone="info" icon="doc" label={t(`upload.kind.${res.kind}`)} />
        </div>
        <p className="text-sm text-ink-600">{t("upload.review_intro")}</p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <ul className="panel flex flex-col divide-y divide-rule overflow-hidden">
          {FIELD_KEYS.map((k) => {
            const f = fields[k];
            const valid = fieldValid(k, f);
            const required = REQUIRED_FIELDS.includes(k);
            const isSel = k === selected;
            const method = f.edited ? "manual" : f.method;
            const methodTone = method === "missing" ? "warn" : method === "llm" ? "info" : "ok";
            return (
              <li key={k} className={`relative flex flex-col gap-2 px-5 py-3.5 transition-colors ${isSel ? "bg-paper" : ""}`}>
                {isSel && <span aria-hidden="true" className="absolute inset-y-0 left-0 w-0.5 bg-saffron-500" />}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label htmlFor={`f-${k}`} className="text-sm font-medium text-ink-800">
                    {t(FIELD_LABEL[k])}
                    {required && <span className="ml-1.5 text-xs font-normal text-ink-500">{t("upload.required")}</span>}
                  </label>
                  <span className="flex items-center gap-2">
                    {method !== "missing" && method !== "manual" && (
                      <span className="num text-xs text-ink-500">{t("upload.confidence", { n: Math.round(f.confidence * 100) })}</span>
                    )}
                    <StatusIcon size="sm" tone={methodTone} label={t(`upload.method.${method}`)} />
                  </span>
                </div>
                <input
                  id={`f-${k}`}
                  className="field-input num"
                  value={f.value ?? ""}
                  aria-invalid={!valid}
                  onFocus={() => setSelected(k)}
                  onChange={(e) => setField(k, e.target.value.trim())}
                  placeholder={FIELD_PATTERN[k] === DATE ? t("common.date_format") : undefined}
                />
              </li>
            );
          })}
        </ul>

        <aside aria-live="polite" className="panel flex flex-col gap-3 self-start p-5 lg:sticky lg:top-20">
          <div className="flex items-center justify-between gap-2">
            <h3 className="eyebrow">{t("upload.source")}</h3>
            {sel.line !== null && sel.line !== undefined && (
              <span className="num text-xs text-ink-500">{t("upload.source_line", { n: sel.line })}</span>
            )}
          </div>
          <p className="text-sm font-medium text-ink-950">{t(FIELD_LABEL[selected])}</p>
          {sel.source_text ? (
            <blockquote className="rounded-md border-l-2 border-saffron-500 bg-paper px-3 py-2.5 font-mono text-[0.8125rem] leading-relaxed text-ink-900">
              {sel.source_text}
            </blockquote>
          ) : (
            <p className="text-sm text-warn">{t("upload.source_none")}</p>
          )}
          <p className="border-t border-rule pt-3 text-xs text-ink-500">{t("upload.machine_note")}</p>
        </aside>
      </div>

      {messages.length > 0 && (
        <section aria-labelledby="msgs-title" className="panel p-6">
          <h3 id="msgs-title" className="section-title">{t("upload.messages_title")}</h3>
          <ol className="mt-4 flex flex-col divide-y divide-rule">
            {messages.map((m) => (
              <li key={m.line} className="grid gap-1.5 py-3 first:pt-0 last:pb-0 sm:grid-cols-[8rem_1fr]">
                <div className="num flex flex-col text-xs text-ink-500">
                  <span>{m.sent ? date(m.sent) : t("upload.source_line", { n: m.line })}</span>
                  {m.days_after_delivery !== null && m.days_after_delivery !== undefined && (
                    <span>{t("upload.msg.day", { n: m.days_after_delivery })}</span>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <p className="text-sm text-ink-900">
                    <span className="font-medium">{m.sender}:</span> {m.text}
                  </p>
                  {(m.tags.length > 0 || m.within_objection_window !== null) && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {m.tags.map((tag) => (
                        <span key={tag} className="tag">{t(`msgtag.${tag}`)}</span>
                      ))}
                      {m.within_objection_window === true && <span className="text-xs text-ink-500">{t("upload.msg.in_window")}</span>}
                      {m.within_objection_window === false && <span className="text-xs text-warn">{t("upload.msg.after_window")}</span>}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {notes.length > 0 && (
        <details className="panel px-6 py-4 text-sm">
          <summary className="cursor-pointer text-sm font-medium text-ink-800">{t("upload.extractor_notes")}</summary>
          <ul className="mt-3 flex flex-col gap-2 text-ink-700">
            {notes.map((w, i) => (
              <li key={`${w.code}-${i}`}>{tWarning(w.code, w.text)}</li>
            ))}
          </ul>
        </details>
      )}

      <section aria-labelledby="details-title" className="panel flex flex-col gap-5 p-6">
        <h3 id="details-title" className="section-title">{t("upload.details_title")}</h3>
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
            <input className="field-input num" placeholder={t("common.date_format")} value={udyamDate} aria-invalid={udyamDate !== "" && !DATE.test(udyamDate)} onChange={(e) => setUdyamDate(e.target.value.trim())} />
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
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-0.5 h-4 w-4 accent-ink-950" checked={hasProof} onChange={(e) => setHasProof(e.target.checked)} />
          <span className="text-ink-900">{t("upload.field.has_delivery_proof")}</span>
        </label>
      </section>

      <div className="sticky bottom-3 z-10 flex flex-wrap items-center gap-3 rounded-xl border border-rule bg-paper-raised/95 px-4 py-3 shadow-float backdrop-blur">
        <button type="button" className="btn btn-primary" disabled={!canApprove} onClick={approve}>
          <Icon name="ok" className="h-4 w-4" />
          {t("upload.approve")}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onCancel}>
          {t("common.close")}
        </button>
        {!canApprove && <span className="text-xs text-ink-500">{t("upload.approve_disabled")}</span>}
      </div>
    </div>
  );
}

export function UploadScreen() {
  const { t, tCode } = useT();
  const input = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function read(blob: Blob, name: string, sample: ExtractionSample | null) {
    setError(null);
    setReading(true);
    try {
      setResult({ response: await extractEvidence(blob, name), offlineSample: false });
    } catch (err) {
      if (err instanceof BackendUnreachable) {
        if (sample) setResult({ response: sample.response, offlineSample: true });
        else setError(t("upload.offline_file"));
      } else {
        setError(err instanceof ApiError ? err.message : t("state.error_title"));
      }
    } finally {
      setReading(false);
    }
  }

  function handle(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (!looksLikeText(file)) {
      setError(t("upload.not_text"));
      return;
    }
    void read(file, file.name, null);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    handle(e.dataTransfer.files?.[0]);
  }

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-[2rem] font-semibold leading-tight tracking-[-0.025em] text-ink-950">{t("upload.title")}</h1>
        <p className="max-w-2xl text-sm text-ink-500">{t("upload.intro")}</p>
      </header>

      {result ? (
        <Review result={result} onCancel={() => setResult(null)} />
      ) : (
        <div className="flex flex-col gap-6">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center gap-4 rounded-xl border border-dashed px-6 py-16 text-center transition-colors ${
              dragOver ? "border-saffron-500 bg-saffron-100/40" : "border-rule-strong bg-paper-raised"
            }`}
          >
            <span className="grid h-11 w-11 place-items-center rounded-xl border border-rule bg-paper text-ink-600">
              <Icon name="upload" className="h-5 w-5" />
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-base font-medium text-ink-950">{reading ? t("upload.reading") : t("upload.drop")}</p>
              <p className="text-sm text-ink-500">{t("upload.drop_hint")}</p>
            </div>
            <input
              ref={input}
              type="file"
              accept=".txt,text/plain"
              className="sr-only"
              id="evidence-file"
              tabIndex={-1}
              aria-label={t("upload.choose")}
              onChange={(e) => handle(e.target.files?.[0])}
            />
            <button type="button" className="btn btn-primary" disabled={reading} onClick={() => input.current?.click()}>
              {t("upload.choose")}
            </button>
          </div>

          {error && (
            <p role="alert" className="flex items-center gap-2 text-sm text-block">
              <Icon name="block" className="h-4 w-4" />
              {error}
            </p>
          )}

          {EXTRACTION_SAMPLES.length > 0 && (
            <div className="flex flex-col gap-3">
              <p className="eyebrow">{t("upload.samples")}</p>
              <div className="flex flex-wrap gap-2">
                {EXTRACTION_SAMPLES.map((s) => (
                  <button
                    key={s.name}
                    type="button"
                    className="btn btn-secondary"
                    disabled={reading}
                    onClick={() => void read(new Blob([s.text], { type: "text/plain" }), s.name, s)}
                  >
                    <Icon name="doc" className="h-4 w-4 text-ink-500" />
                    {tCode("upload.sample", s.name, s.name)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <JudgeConsole current={null} />
    </div>
  );
}

