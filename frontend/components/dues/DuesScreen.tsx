"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BackendUnreachable, evaluate, getPresetRequest, listPresets, offlineResponseFor } from "@/lib/api";
import { getUploaded, listUploadedIds } from "@/lib/caseStore";
import { currentStage, isNotCovered, isPlaceholder } from "@/lib/derive";
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
  kind: "preset" | "upload";
  request: CaseRequest;
  response: CaseResponse | null;
};

async function evaluateRow(id: string, kind: Row["kind"], request: CaseRequest): Promise<Row> {
  try {
    return { id, kind, request, response: await evaluate(request) };
  } catch (e) {
    const fixture = e instanceof BackendUnreachable && kind === "preset" ? offlineResponseFor(id) : null;
    return { id, kind, request, response: fixture };
  }
}

async function loadRows(): Promise<Row[]> {
  const presets = await listPresets();
  const presetRows = await Promise.all(
    presets.data.map(async (p) => {
      try {
        const r = await getPresetRequest(p.id);
        return evaluateRow(p.id, "preset", r.data.request);
      } catch {
        return null;
      }
    }),
  );
  const uploadRows = await Promise.all(
    listUploadedIds().flatMap((id) => {
      const req = getUploaded(id);
      return req ? [evaluateRow(id, "upload", req)] : [];
    }),
  );
  return [...uploadRows, ...presetRows.filter((r): r is Row => r !== null)];
}

/** Urgency: most days overdue first; rows without engine figures last. */
function byUrgency(a: Row, b: Row): number {
  const da = a.response?.timeline?.days_overdue ?? -1;
  const db = b.response?.timeline?.days_overdue ?? -1;
  return db - da;
}

const GRID = "md:grid-cols-[minmax(0,2fr)_minmax(0,1.55fr)_minmax(0,0.8fr)_minmax(0,1.1fr)_minmax(0,1.25fr)_1.25rem]";

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
    <li>
      <Link
        href={href(target)}
        className={`group grid grid-cols-2 items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-paper ${GRID}`}
      >
        <div className="col-span-2 flex min-w-0 flex-col gap-0.5 md:col-span-1">
          <span className="truncate font-medium text-ink-950">{row.request.buyer.name}</span>
          <span className="num flex items-center gap-2 truncate text-xs text-ink-500">
            {row.id}
            {row.kind === "upload" && <span className="rounded-full bg-paper-sunk px-1.5 font-sans">{t("dues.row.uploaded")}</span>}
          </span>
        </div>

        <div>{res && <EligibilityPill status={res.jurisdiction.status} />}</div>

        <div className="num text-sm">
          {!res ? (
            <span className="text-ink-500">{t("dues.row.needs_backend")}</span>
          ) : days !== null && days > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-warn">
              <Icon name="clock" className="h-3.5 w-3.5" />
              {t("dues.row.overdue", { n: count(days) })}
            </span>
          ) : days === null ? (
            <span className="text-ink-500">{t("dues.row.no_date")}</span>
          ) : (
            <span className="text-ink-600">{t("dues.row.not_due")}</span>
          )}
        </div>

        <div className="text-sm md:text-right">
          {res?.financials ? (
            <Money value={res.financials.total_claim} placeholder={placeholder} className="font-medium text-ink-950" />
          ) : (
            <span className="text-ink-300">—</span>
          )}
        </div>

        <div className="text-sm text-ink-700">
          {notCovered ? (
            <StatusIcon size="sm" tone="block" label={t("dues.row.not_covered")} />
          ) : stage ? (
            <span className="truncate">
              <span className="num mr-1.5 text-xs text-ink-500">{stage}</span>
              {t(`stage.${stage}.title`)}
            </span>
          ) : null}
        </div>

        <Icon name="chevron" className="hidden h-4 w-4 text-ink-300 transition-colors group-hover:text-ink-950 md:block" />
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

  const placeholder = Boolean(rows?.some((r) => isPlaceholder(r.response)));
  const buyers = rows ? new Set(rows.map((r) => r.request.buyer.name)).size : 0;
  const overdue = rows ? rows.filter((r) => (r.response?.timeline?.days_overdue ?? 0) > 0) : [];
  const maxDays = overdue.reduce<number | null>((m, r) => {
    const d = r.response?.timeline?.days_overdue ?? null;
    return d !== null && (m === null || d > m) ? d : m;
  }, null);

  const stats = [
    { label: t("dues.summary.buyers"), value: rows ? count(buyers) : null },
    { label: t("dues.summary.overdue"), value: rows ? count(overdue.length) : null },
    { label: t("dues.summary.oldest"), value: rows ? (maxDays === null ? "—" : t("dues.summary.days", { n: count(maxDays) })) : null },
  ];

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-[2rem] font-semibold leading-tight tracking-[-0.025em] text-ink-950">{t("dues.title")}</h1>
          <p className="text-sm text-ink-500">{t("dues.subtitle")}</p>
        </div>
        <Link href={href("/upload")} className="btn btn-primary self-start sm:self-auto">
          <Icon name="upload" className="h-4 w-4" />
          {t("nav.upload")}
        </Link>
      </header>

      <DataBanners placeholder={placeholder} />

      <div className="flex flex-col gap-2">
        <dl className="panel grid grid-cols-3 divide-x divide-rule">
          {stats.map((s) => (
            <div key={s.label} className="flex flex-col gap-2 px-5 py-4 sm:px-6 sm:py-5">
              <dt className="text-xs text-ink-500">{s.label}</dt>
              <dd className="figure text-2xl text-ink-950 sm:text-[1.75rem]">{s.value ?? <Skeleton className="h-7 w-14" />}</dd>
            </div>
          ))}
        </dl>
        <p className="px-1 text-xs text-ink-500">{t("dues.summary.note")}</p>
      </div>

      {rows === null ? (
        <div className="panel flex flex-col gap-3 p-5" aria-busy="true">
          <span className="sr-only">{t("state.loading")}</span>
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState title={t("dues.empty.title")} body={t("dues.empty.body")}>
          <Link href={href("/upload")} className="btn btn-primary">{t("nav.upload")}</Link>
        </EmptyState>
      ) : (
        <div className="panel overflow-hidden">
          <div className={`hidden gap-x-4 border-b border-rule bg-paper px-5 py-2.5 text-xs font-medium text-ink-500 md:grid ${GRID}`} aria-hidden="true">
            <span>{t("dues.col.buyer")}</span>
            <span>{t("dues.col.status")}</span>
            <span>{t("dues.col.overdue")}</span>
            <span className="text-right">{t("dues.col.claim")}</span>
            <span>{t("dues.col.stage")}</span>
            <span />
          </div>
          <ul aria-label={t("dues.list_label")} className="divide-y divide-rule">
            {rows.map((r) => (
              <BuyerRow key={r.id} row={r} />
            ))}
          </ul>
        </div>
      )}

      <JudgeConsole current={null} />
    </div>
  );
}
