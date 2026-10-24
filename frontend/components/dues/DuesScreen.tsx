"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BackendUnreachable, evaluate, getPresetRequest, listPresets, offlineResponseFor } from "@/lib/api";
import { getUploaded, listUploadedIds } from "@/lib/caseStore";
import { currentStage, isNotCovered, isPlaceholder } from "@/lib/derive";
import { DEMO_CASES } from "@/lib/fixtures";
import { count } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { EmptyState, Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { DataBanners } from "../shell/Banners";
import { JudgeConsole } from "../shell/JudgeConsole";
import { EligibilityPill } from "../case/EligibilityPill";

type Row = {
  id: string;
  title: string;
  kind: "preset" | "demo" | "upload";
  request: CaseRequest;
  response: CaseResponse | null;
  offline: boolean;
};

async function evaluateRow(id: string, title: string, kind: Row["kind"], request: CaseRequest): Promise<Row> {
  try {
    return { id, title, kind, request, response: await evaluate(request), offline: false };
  } catch (e) {
    const offline = e instanceof BackendUnreachable;
    const fixture = offline && kind === "preset" ? offlineResponseFor(id) : null;
    return { id, title, kind, request, response: fixture, offline };
  }
}

async function loadRows(): Promise<Row[]> {
  const presets = await listPresets();
  const presetRows = await Promise.all(
    presets.data.map(async (p) => {
      try {
        const r = await getPresetRequest(p.id);
        return evaluateRow(p.id, r.data.title, "preset", r.data.request);
      } catch {
        return null;
      }
    }),
  );
  const presetIds = new Set(presets.data.map((p) => p.id));
  const demoRows = await Promise.all(
    DEMO_CASES.filter((d) => !presetIds.has(d.id)).map((d) => evaluateRow(d.id, d.title, "demo", d.request)),
  );
  const uploadRows = await Promise.all(
    listUploadedIds().flatMap((id) => {
      const req = getUploaded(id);
      return req ? [evaluateRow(id, id, "upload", req)] : [];
    }),
  );
  return [...uploadRows, ...presetRows.filter((r): r is Row => r !== null), ...demoRows];
}

/** Urgency: most days overdue first; rows without engine numbers last. */
function byUrgency(a: Row, b: Row): number {
  const da = a.response?.timeline?.days_overdue ?? -1;
  const db = b.response?.timeline?.days_overdue ?? -1;
  return db - da;
}

function BuyerRow({ row }: { row: Row }) {
  const { t } = useT();
  const href = useHref();
  const res = row.response;
  const placeholder = isPlaceholder(res);
  const days = res?.timeline?.days_overdue ?? null;
  const notCovered = res ? isNotCovered(res) : false;
  const stage = res && !notCovered ? currentStage(res) : null;
  const target = notCovered ? `/eligibility/${row.id}` : `/case/${row.id}`;

  return (
    <li className="panel grid gap-3 p-4 transition-colors hover:border-ink-600 sm:grid-cols-[1.6fr_1fr_1fr_auto] sm:items-center sm:gap-5 sm:px-5">
      <div className="flex min-w-0 flex-col gap-1">
        <Link href={href(target)} className="font-display text-lg font-semibold leading-snug text-ink-950 underline-offset-4 hover:underline">
          {row.request.buyer.name}
        </Link>
        <span className="flex flex-wrap items-center gap-2 text-xs text-ink-600">
          <span className="num">{row.id}</span>
          {row.kind === "demo" && <StatusIcon size="sm" tone="info" icon="info" label={t("badge.demo")} />}
          {res && <EligibilityPill status={res.jurisdiction.status} />}
        </span>
      </div>

      <div className="flex flex-col">
        <span className="text-xs uppercase tracking-wide text-ink-500">{t("dues.row.claim")}</span>
        {res?.financials ? (
          <Money value={res.financials.total_claim} placeholder={placeholder} className="text-lg font-semibold" />
        ) : (
          <span className="text-sm text-ink-600">{res ? "—" : t("dues.row.needs_backend")}</span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {days !== null && days > 0 ? (
          <StatusIcon tone="warn" icon="clock" label={t("dues.row.overdue", { n: count(days) })} />
        ) : res ? (
          <StatusIcon tone="ok" label={t("dues.row.not_due")} />
        ) : null}
        {stage && <span className="rounded-sm border border-ink-300 px-1.5 py-0.5 text-xs font-semibold text-ink-700">{t("stage.chip", { n: stage })}</span>}
      </div>

      <Link href={href(target)} className="btn btn-secondary justify-self-start sm:justify-self-end">
        {t("dues.row.next_step")}
        <Icon name="arrow-right" className="h-4 w-4" />
      </Link>
    </li>
  );
}

export function DuesScreen() {
  const { t } = useT();
  const href = useHref();
  const [rows, setRows] = useState<Row[] | null>(null);

  useEffect(() => {
    let alive = true;
    loadRows().then((r) => alive && setRows([...r].sort(byUrgency)));
    return () => {
      alive = false;
    };
  }, []);

  const offline = Boolean(rows?.some((r) => r.offline));
  const placeholder = Boolean(rows?.some((r) => isPlaceholder(r.response)));
  const buyers = rows ? new Set(rows.map((r) => r.request.buyer.name)).size : 0;
  const overdue = rows ? rows.filter((r) => (r.response?.timeline?.days_overdue ?? 0) > 0) : [];
  const maxDays = overdue.reduce<number | null>((m, r) => {
    const d = r.response?.timeline?.days_overdue ?? null;
    return d !== null && (m === null || d > m) ? d : m;
  }, null);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-ink-950">{t("dues.title")}</h1>
          <p className="mt-1 text-ink-700">{t("dues.subtitle")}</p>
        </div>
        <Link href={href("/upload")} className="btn btn-primary self-start">
          <Icon name="upload" className="h-4 w-4" />
          {t("nav.upload")}
        </Link>
      </header>

      <DataBanners offline={offline} placeholder={placeholder} />

      <dl className="grid grid-cols-3 divide-x divide-rule rounded-md border border-rule bg-paper-raised">
        {[
          { label: t("dues.summary.buyers"), value: rows ? count(buyers) : null },
          { label: t("dues.summary.overdue"), value: rows ? count(overdue.length) : null },
          { label: t("dues.summary.oldest"), value: rows ? count(maxDays) : null },
        ].map((s) => (
          <div key={s.label} className="flex flex-col gap-1 px-4 py-3 sm:px-5">
            <dt className="text-xs uppercase tracking-wide text-ink-500">{s.label}</dt>
            <dd className="num text-2xl font-medium text-ink-950">{s.value ?? <Skeleton className="h-7 w-12" />}</dd>
          </div>
        ))}
      </dl>
      <p className="-mt-3 text-xs text-ink-500">{t("dues.summary.note")}</p>

      {rows === null ? (
        <div className="flex flex-col gap-3" aria-busy="true">
          <span className="sr-only">{t("state.loading")}</span>
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title={t("dues.empty.title")} body={t("dues.empty.body")}>
          <Link href={href("/upload")} className="btn btn-primary">{t("nav.upload")}</Link>
        </EmptyState>
      ) : (
        <ul aria-label={t("dues.list_label")} className="flex flex-col gap-3">
          {rows.map((r) => (
            <BuyerRow key={r.id} row={r} />
          ))}
        </ul>
      )}

      <JudgeConsole current={null} />
    </div>
  );
}
