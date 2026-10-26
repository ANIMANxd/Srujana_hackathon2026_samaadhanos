"use client";

// Bring in past invoices from a CSV. Three steps, and nothing is stored until
// the last one: choose a file, read the preview (a dry run), then "Import N
// rows". The server does the checking and the customer matching; this screen
// shows what it sends and the plain message for each row that has a problem.

import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";
import { ApiError, BackendUnreachable, confirmImport, previewImport } from "@/lib/api";
import { bookAction, announceBookChange } from "@/lib/customerBook";
import { count } from "@/lib/format";
import { idempotencyKeyFor, releaseIdempotencyKey } from "@/lib/idempotency";
import { previewView, resultCustomerIds, templateCsv } from "@/lib/importRows";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { ImportPreview, ImportResult } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { PreviewTable } from "./PreviewTable";

const MAX_MB = 5;
const MAX_BYTES = MAX_MB * 1024 * 1024;
const LIST_LIMIT = 50;

type Stage =
  | { name: "choose" }
  | { name: "preview"; preview: ImportPreview; file: string }
  | { name: "done"; result: ImportResult };

function isCsv(f: File): boolean {
  return /\.csv$/i.test(f.name) || f.type === "text/csv";
}

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([templateCsv()], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "samaadhan-invoices-template.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 bg-white px-4 py-3">
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="figure text-lg text-ink-950">{count(value)}</dd>
    </div>
  );
}

function MoreNote({ n }: { n: number }) {
  const { t } = useT();
  return <p className="text-xs text-ink-500">{t("import.more", { n: count(n) })}</p>;
}

function Messages({ title, items, tone }: { title: string; items: string[]; tone: "warn" | "block" }) {
  if (items.length === 0) return null;
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-sm font-semibold text-ink-950">{title}</h3>
      <ul className="flex flex-col gap-1">
        {items.slice(0, LIST_LIMIT).map((m, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-ink-800">
            <Icon name={tone === "warn" ? "warn" : "block"} className={`mt-0.5 h-4 w-4 shrink-0 ${tone === "warn" ? "text-warn" : "text-block"}`} />
            <span className="break-words">{m}</span>
          </li>
        ))}
      </ul>
      {items.length > LIST_LIMIT && <MoreNote n={items.length - LIST_LIMIT} />}
    </section>
  );
}

export function ImportScreen() {
  const { t } = useT();
  const href = useHref();
  const input = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>({ name: "choose" });
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const working = useRef(false);

  function fail(e: unknown) {
    if (e instanceof BackendUnreachable) setError(t("import.unreachable"));
    else if (e instanceof ApiError && e.status === 404 && e.message === "Not Found") setError(t("import.not_available"));
    else setError(e instanceof ApiError ? e.message : t("import.failed"));
  }

  async function choose(file: File | undefined) {
    setError(null);
    if (!file || working.current) return;
    if (!isCsv(file)) return setError(t("import.not_csv"));
    if (file.size > MAX_BYTES) return setError(t("import.too_big", { mb: count(MAX_MB) }));
    if (file.size === 0) return setError(t("import.empty_file"));
    working.current = true;
    setBusy(true);
    const actionId = bookAction.previewImport(file.name, file.size, file.lastModified);
    try {
      const preview = await previewImport(file, file.name, { idempotencyKey: idempotencyKeyFor(actionId) });
      releaseIdempotencyKey(actionId);
      setStage({ name: "preview", preview, file: file.name });
    } catch (e) {
      if (!(e instanceof BackendUnreachable)) releaseIdempotencyKey(actionId);
      fail(e);
    } finally {
      working.current = false;
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function commit(preview: ImportPreview) {
    if (working.current) return;
    working.current = true;
    setBusy(true);
    setError(null);
    const actionId = bookAction.confirmImport(preview.preview_id);
    try {
      const result = await confirmImport(preview.preview_id, { idempotencyKey: idempotencyKeyFor(actionId) });
      releaseIdempotencyKey(actionId);
      announceBookChange();
      setStage({ name: "done", result });
    } catch (e) {
      if (!(e instanceof BackendUnreachable)) releaseIdempotencyKey(actionId);
      fail(e);
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    void choose(e.dataTransfer.files?.[0]);
  }

  const err = error && (
    <p role="alert" className="flex items-start gap-2 text-sm text-block">
      <Icon name="block" className="mt-0.5 h-4 w-4 shrink-0" />
      {error}
    </p>
  );

  return (
    <div className="flex flex-col gap-6">
      <Link href={href("/")} className="inline-flex items-center gap-1.5 self-start text-sm text-ink-600 hover:text-ink-950">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("review.back")}
      </Link>
      <header className="flex flex-col gap-1">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-ink-950">{t("import.title")}</h1>
        <p className="max-w-2xl text-sm text-ink-500">{t("import.intro")}</p>
      </header>

      {stage.name === "choose" && (
        <div className="flex flex-col gap-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center gap-4 rounded-xl border border-dashed px-6 py-14 text-center transition-colors ${
              dragOver ? "border-saffron-500 bg-saffron-100/40" : "border-rule-strong bg-paper-raised"
            }`}
          >
            <span className="grid h-11 w-11 place-items-center rounded-xl border border-rule bg-paper text-ink-600">
              <Icon name="upload" className="h-5 w-5" />
            </span>
            <div className="flex flex-col gap-1">
              <p className="text-base font-medium text-ink-950">{busy ? t("import.reading") : t("import.drop")}</p>
              <p className="text-sm text-ink-500">{t("import.drop_hint", { mb: count(MAX_MB) })}</p>
            </div>
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              tabIndex={-1}
              aria-label={t("import.choose")}
              onChange={(e) => void choose(e.target.files?.[0])}
            />
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => input.current?.click()}>
              {t("import.choose")}
            </button>
          </div>
          {err}
          <p className="text-sm text-ink-600">
            <button type="button" className="link" onClick={downloadTemplate}>
              {t("import.template")}
            </button>
            <span className="text-ink-500"> · {t("import.template_note")}</span>
          </p>
        </div>
      )}

      {stage.name === "preview" && <PreviewStep stage={stage} busy={busy} err={err} onCommit={() => void commit(stage.preview)} onBack={() => (setError(null), setStage({ name: "choose" }))} />}

      {stage.name === "done" && <DoneStep result={stage.result} onAgain={() => (setError(null), setStage({ name: "choose" }))} />}
    </div>
  );
}

function PreviewStep({
  stage,
  busy,
  err,
  onCommit,
  onBack,
}: {
  stage: Extract<Stage, { name: "preview" }>;
  busy: boolean;
  err: React.ReactNode;
  onCommit: () => void;
  onBack: () => void;
}) {
  const { t } = useT();
  const p = stage.preview;
  const view = previewView(p);
  const warnings = p.warnings ?? [];
  const errors = p.errors ?? [];
  return (
    <div className="flex flex-col gap-5">
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
        <StatusIcon size="sm" tone="info" icon="doc" label={t("import.preview_of", { file: stage.file })} />
        <span className="text-ink-500">{t("import.nothing_stored")}</span>
      </p>

      <section aria-label={t("import.summary")}>
        <dl className="panel grid grid-cols-2 gap-px overflow-hidden bg-rule sm:grid-cols-4">
          <Stat label={t("import.sum.total")} value={p.total_rows} />
          <Stat label={t("import.sum.ready")} value={p.valid_rows} />
          <Stat label={t("import.sum.warnings")} value={view.warningRows ?? warnings.length} />
          <Stat label={t("import.sum.errors")} value={p.invalid_rows} />
        </dl>
        {p.invalid_rows > 0 && <p className="mt-1.5 text-xs text-ink-500">{t("import.errors_skipped")}</p>}
      </section>

      {view.rows.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {!view.checked && (
            <p className="flex items-start gap-2 text-sm text-ink-600">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
              {t("import.sample_only", { shown: count(view.rows.length), total: count(p.total_rows) })}
            </p>
          )}
          <PreviewTable rows={view.rows} columns={view.columns} />
        </div>
      ) : (
        <p className="text-sm text-ink-600">{t("import.no_rows")}</p>
      )}

      <Messages title={t("import.errors")} items={errors} tone="block" />
      <Messages title={t("import.warnings")} items={warnings} tone="warn" />
      {err}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-primary" onClick={onCommit} disabled={busy || p.valid_rows === 0} aria-busy={busy}>
          {t("import.commit", { n: count(p.valid_rows) })}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onBack} disabled={busy}>
          {t("import.other_file")}
        </button>
      </div>
      {p.valid_rows === 0 && <p className="text-sm text-ink-600">{t("import.none_ready")}</p>}
    </div>
  );
}

function DoneStep({ result, onAgain }: { result: ImportResult; onAgain: () => void }) {
  const { t } = useT();
  const href = useHref();
  const cases = result.case_ids ?? [];
  const customers = resultCustomerIds(result);
  return (
    <div className="flex flex-col gap-5" aria-live="polite">
      <p className="flex items-center gap-2 text-base font-semibold text-ink-950">
        <StatusIcon tone={result.failed > 0 ? "warn" : "ok"} icon={result.failed > 0 ? "warn" : "ok"} label={t("import.done", { n: count(result.imported) })} />
      </p>
      <dl className="panel grid grid-cols-2 gap-px overflow-hidden bg-rule sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={t("import.res.created")} value={result.imported} />
        <Stat label={t("import.res.skipped")} value={result.skipped} />
        <Stat label={t("import.res.errors")} value={result.failed} />
        <Stat label={t("import.res.customers_created")} value={result.customers_created} />
        <Stat label={t("import.res.customers_matched")} value={result.customers_matched} />
        <Stat label={t("import.res.gstins")} value={result.gstins_attached} />
      </dl>

      <Messages title={t("import.errors")} items={result.errors ?? []} tone="block" />
      <Messages title={t("import.warnings")} items={result.warnings ?? []} tone="warn" />

      {(customers.length > 0 || cases.length > 0) && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-ink-950">{t("import.affected")}</h3>
          <ul className="flex flex-wrap gap-2">
            {customers.slice(0, LIST_LIMIT).map((id, i) => (
              <li key={id}>
                <Link href={href(`/customers/${encodeURIComponent(id)}`)} className="btn btn-secondary min-h-8 px-3 text-xs">
                  {t("import.open_customer", { n: count(i + 1) })}
                </Link>
              </li>
            ))}
            {customers.length === 0 &&
              cases.slice(0, LIST_LIMIT).map((id, i) => (
                <li key={id}>
                  <Link href={href(`/case/${encodeURIComponent(id)}`)} className="btn btn-secondary min-h-8 px-3 text-xs">
                    {t("import.open_invoice", { n: count(i + 1) })}
                  </Link>
                </li>
              ))}
          </ul>
          {Math.max(customers.length, cases.length) > LIST_LIMIT && <MoreNote n={Math.max(customers.length, cases.length) - LIST_LIMIT} />}
        </section>
      )}

      <div className="flex flex-wrap gap-2">
        <Link href={href("/")} className="btn btn-primary">
          {t("import.see_customers")}
        </Link>
        <button type="button" className="btn btn-secondary" onClick={onAgain}>
          {t("import.another")}
        </button>
      </div>
    </div>
  );
}
