"use client";

// The duplicates review: each suggestion side by side (names, GSTINs, invoice
// counts, how alike the names look) with the actions its kind allows. Nothing is
// applied until the owner picks one, every action answers with an Undo toast, and
// "link as group" never merges: each company keeps its own invoices and duties.

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { attachCustomer, createGroup, dismissSuggestion, getCustomer, linkToGroup, listSuggestions } from "@/lib/api";
import { announceBookChange, bookAction, useBookRead } from "@/lib/customerBook";
import { count } from "@/lib/format";
import { offlineCustomerProfile } from "@/lib/fixturesV5";
import { useT } from "@/lib/i18n";
import { newChangeId, recordChange, type ReviewChange } from "@/lib/reviewLog";
import type { CustomerRow, Suggestion } from "@/lib/types";
import { useCustomers } from "@/lib/useCustomers";
import { IdempotentButton } from "../common/IdempotentButton";
import { ErrorState, Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";
import type { UndoToastState } from "./UndoToast";

type T = ReturnType<typeof useT>["t"];

/** "0.94" -> 94. A display rounding of a ratio the server sent, not a legal figure. */
function alikePct(similarity: string): string {
  const n = Number(similarity);
  return count(Number.isFinite(n) ? Math.round(n * 100) : 0);
}

/** GSTINs per customer id, read from each profile; `null` while unknown. */
function useGstins(ids: string[], live: boolean): Map<string, string[]> {
  const [found, setFound] = useState<Map<string, string[]>>(new Map());
  const key = `${live}:${ids.join(",")}`;
  useEffect(() => {
    let alive = true;
    Promise.all(
      ids.map(async (id) => {
        if (!live) {
          const sample = offlineCustomerProfile();
          return [id, sample?.customer.id === id ? (sample.customer.gstins ?? []) : null] as const;
        }
        try {
          const r = await getCustomer(id);
          return [id, r.source === "live" ? (r.data.customer.gstins ?? []) : null] as const;
        } catch {
          return [id, null] as const;
        }
      }),
    ).then((pairs) => {
      if (!alive) return;
      const next = new Map<string, string[]>();
      for (const [id, g] of pairs) if (g) next.set(id, g);
      setFound(next);
    });
    return () => {
      alive = false;
    };
    // `key` names the request; `ids` is a fresh array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return found;
}

function Party({ row, id, gstins, t }: { row: CustomerRow | undefined; id: string; gstins: string[] | undefined; t: T }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-rule bg-white p-3">
      <p className="break-words font-medium text-ink-950">{row?.display_name ?? id}</p>
      <p className="text-xs text-ink-600">
        {row?.kind === "PAN" ? t("profile.pan", { pan: row.pan ?? "" }) : t("profile.provisional")}
      </p>
      {gstins !== undefined ? (
        gstins.length === 0 ? (
          <p className="text-xs text-ink-600">{t("review.no_gstin")}</p>
        ) : (
          <ul aria-label={t("profile.gstins")} className="flex flex-col gap-0.5">
            {gstins.map((g) => (
              <li key={g} className="num text-xs text-ink-700">
                {g}
              </li>
            ))}
          </ul>
        )
      ) : row ? (
        <p className="text-xs text-ink-600">{row.gstin_count === 0 ? t("review.no_gstin") : t("review.gstin_count", { n: count(row.gstin_count) })}</p>
      ) : null}
      {row && <p className="text-xs text-ink-600">{t("review.invoices", { n: count(row.invoice_count) })}</p>}
    </div>
  );
}

function Card({
  s,
  rows,
  gstins,
  offline,
  refresh,
  toast,
  onActed,
}: {
  s: Suggestion;
  rows: Map<string, CustomerRow>;
  gstins: Map<string, string[]>;
  offline: boolean;
  refresh: () => void;
  toast: UndoToastState;
  onActed: () => void;
}) {
  const { t } = useT();
  const noteId = useId();
  const a = rows.get(s.a);
  const b = rows.get(s.b);
  const nameA = a?.display_name ?? s.a;
  const nameB = b?.display_name ?? s.b;
  // If one side already sits in a group the other joins it; no new group, so no label to ask for.
  const existing = a?.group_id ? { id: a.group_id, label: a.group_label ?? "", holder: nameA, joiner: s.b, joinerName: nameB } : b?.group_id ? { id: b.group_id, label: b.group_label ?? "", holder: nameB, joiner: s.a, joinerName: nameA } : null;
  const [label, setLabel] = useState("");
  const typed = label.trim();
  const made = useRef<ReviewChange | null>(null);

  const finish = (change: ReviewChange, message: string) => {
    recordChange(change);
    announceBookChange();
    refresh();
    onActed();
    toast.show(change, message);
  };

  return (
    <li className="flex flex-col gap-3 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusIcon size="sm" tone="info" icon="info" label={t(`review.kind.${s.kind}`)} />
        <p className="num text-xs text-ink-600">{t("review.similarity", { pct: alikePct(s.similarity) })}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Party row={a} id={s.a} gstins={gstins.get(s.a)} t={t} />
        <Party row={b} id={s.b} gstins={gstins.get(s.b)} t={t} />
      </div>
      <p className="text-sm text-ink-600">{s.reason}</p>

      {s.kind === "ATTACH" ? (
        <p className="text-sm text-ink-800">
          {t((gstins.get(s.a)?.length ?? a?.gstin_count ?? 1) === 0 ? "review.attach.explain_no_gstin" : "review.attach.explain", { name: nameB })}
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {existing ? (
            <p className="text-sm text-ink-800">{t("review.group.joins", { name: existing.holder, label: existing.label, other: existing.joinerName })}</p>
          ) : (
            <label className="block max-w-sm">
              <span className="field-label">{t("review.group.label")}</span>
              <input
                className="field-input"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                maxLength={80}
                aria-describedby={noteId}
              />
            </label>
          )}
          <p id={noteId} className="text-xs text-ink-600">
            {t("review.group.note")}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-start gap-2">
        {s.kind === "ATTACH" ? (
          <IdempotentButton
            actionId={bookAction.attachCustomer(s.b, s.a)}
            run={async (opts) => {
              await attachCustomer(s.b, s.a, opts);
              made.current = { id: newChangeId(), kind: "ATTACH", at: new Date().toISOString(), sourceId: s.a, targetId: s.b, sourceName: nameA, targetName: nameB };
            }}
            onConflict={refresh}
            onDone={() => made.current && finish(made.current, t("review.toast.attach", { source: nameA, target: nameB }))}
            offline={offline}
          >
            {t("review.attach.button")}
          </IdempotentButton>
        ) : (
          <IdempotentButton
            actionId={existing ? bookAction.linkToGroup(existing.id, existing.joiner) : bookAction.createGroup(typed, [s.a, s.b])}
            run={async (opts) => {
              const id = newChangeId();
              const at = new Date().toISOString();
              if (existing) {
                await linkToGroup(existing.id, existing.joiner, opts);
                made.current = { id, kind: "GROUP", at, groupId: existing.id, label: existing.label, memberIds: [existing.joiner] };
              } else {
                const g = await createGroup(typed, [s.a, s.b], opts);
                made.current = { id, kind: "GROUP", at, groupId: g.id, label: typed, memberIds: [s.a, s.b] };
              }
            }}
            onConflict={refresh}
            onDone={() => {
              const c = made.current;
              if (!c || c.kind !== "GROUP") return;
              finish(
                c,
                existing
                  ? t("review.toast.joined", { name: existing.joinerName, label: c.label })
                  : t("review.toast.group", { a: nameA, b: nameB, label: c.label }),
              );
            }}
            offline={offline}
            disabled={!existing && typed === ""}
          >
            {t("review.group.button")}
          </IdempotentButton>
        )}
        <IdempotentButton
          actionId={bookAction.dismissSuggestion(s.a, s.b)}
          run={async (opts) => {
            await dismissSuggestion(s.a, s.b, opts);
            made.current = { id: newChangeId(), kind: "DISMISS", at: new Date().toISOString(), a: s.a, b: s.b };
          }}
          onConflict={refresh}
          onDone={() => made.current && finish(made.current, t("review.toast.dismiss"))}
          offline={offline}
          className="btn btn-secondary"
        >
          {t("review.dismiss")}
        </IdempotentButton>
      </div>
    </li>
  );
}

export function SuggestionsPanel({ toast }: { toast: UndoToastState }) {
  const { t } = useT();
  const read = useBookRead("suggestions", true, listSuggestions, "customers.load_failed");
  const book = useCustomers({ sort: "display_name", dir: "asc", grouped: false });
  const rows = useMemo(() => new Map((book.rows ?? []).map((r) => [r.id, r])), [book.rows]);
  const ids = useMemo(() => [...new Set((read.data ?? []).flatMap((s) => [s.a, s.b]))], [read.data]);
  const gstins = useGstins(ids, read.source === "live");
  const heading = useRef<HTMLParagraphElement>(null);
  const offline = read.source !== "live";

  if (read.error && !read.data) return <ErrorState message={read.error.detail ?? t(read.error.key)} onRetry={read.refresh} />;
  if (!read.data) return <Skeleton className="h-24" />;

  return (
    <div className="flex flex-col gap-4">
      {read.source === "offline" && <Banner tone="warn" icon="lock" message="book.offline_sample" />}
      <p ref={heading} tabIndex={-1} className="text-sm font-medium text-ink-800 outline-none" aria-live="polite">
        {read.data.length === 0 ? t("review.empty") : t("review.count", { n: count(read.data.length) })}
      </p>
      {read.data.length > 0 && (
        <ul className="panel divide-y divide-rule">
          {read.data.map((s) => (
            <Card
              key={`${s.a}:${s.b}`}
              s={s}
              rows={rows}
              gstins={gstins}
              offline={offline}
              refresh={() => {
                read.refresh();
                book.refresh();
              }}
              toast={toast}
              onActed={() => heading.current?.focus()}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
