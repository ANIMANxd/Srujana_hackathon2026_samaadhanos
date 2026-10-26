"use client";

// The CSV preview: one line per row with its status (icon and words), the
// customer it would join, and the file's own cells. Past 200 rows only the rows
// in view are drawn (fixed row height, spacer rows above and below), and
// aria-rowcount / aria-rowindex keep screen readers oriented in the full list.

import { useRef, useState } from "react";
import { count } from "@/lib/format";
import type { ImportRowView, RowMatch, RowStatus } from "@/lib/importRows";
import { useT } from "@/lib/i18n";
import { StatusIcon } from "../common/StatusIcon";

export const VIRTUAL_OVER = 200;
const ROW_H = 48;
const VIEW_H = 440;
const OVERSCAN = 8;

type T = ReturnType<typeof useT>["t"];

function Status({ row, t }: { row: ImportRowView; t: T }) {
  const map: Record<RowStatus, { tone: "ok" | "warn" | "block" | "info"; icon: "ok" | "warn" | "block" | "info" }> = {
    ready: { tone: "ok", icon: "ok" },
    warning: { tone: "warn", icon: "warn" },
    error: { tone: "block", icon: "block" },
    unchecked: { tone: "info", icon: "info" },
  };
  const m = map[row.status];
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <StatusIcon size="sm" tone={m.tone} icon={m.icon} label={t(`import.status.${row.status}`)} />
      {row.message && (
        <span className="truncate text-xs text-ink-600" title={row.message}>
          {row.message}
        </span>
      )}
    </div>
  );
}

function matchText(m: RowMatch, t: T): string {
  switch (m.kind) {
    case "existing":
      return t("import.match.existing", { name: m.name ?? t("import.match.unnamed") });
    case "new":
      return t("import.match.new");
    case "provisional":
      return t("import.match.provisional");
    default:
      return t("import.match.unknown");
  }
}

export function PreviewTable({ rows, columns }: { rows: ImportRowView[]; columns: string[] }) {
  const { t } = useT();
  const [top, setTop] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const virtual = rows.length > VIRTUAL_OVER;

  const first = virtual ? Math.max(0, Math.floor(top / ROW_H) - OVERSCAN) : 0;
  const last = virtual ? Math.min(rows.length, Math.ceil((top + VIEW_H) / ROW_H) + OVERSCAN) : rows.length;
  const shown = rows.slice(first, last);
  const span = 3 + columns.length;

  return (
    <div
      ref={box}
      tabIndex={0}
      role="region"
      aria-label={t("import.table_label", { n: count(rows.length) })}
      onScroll={virtual ? (e) => setTop(e.currentTarget.scrollTop) : undefined}
      className="panel overflow-auto focus-visible:outline-2 focus-visible:outline-offset-2"
      style={{ maxHeight: VIEW_H }}
    >
      <table className="w-full min-w-[56rem] table-fixed text-left text-sm" aria-rowcount={rows.length + 1}>
        <caption className="sr-only">{t("import.table_label", { n: count(rows.length) })}</caption>
        <thead className="sticky top-0 z-10 border-b border-rule bg-paper text-xs text-ink-500">
          <tr aria-rowindex={1}>
            <th scope="col" className="w-16 px-3 py-2.5 font-medium">
              {t("import.col.row")}
            </th>
            <th scope="col" className="w-56 px-3 py-2.5 font-medium">
              {t("import.col.status")}
            </th>
            <th scope="col" className="w-64 px-3 py-2.5 font-medium">
              {t("import.col.customer")}
            </th>
            {columns.map((c) => (
              <th key={c} scope="col" className="px-3 py-2.5 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {virtual && first > 0 && (
            <tr aria-hidden="true" style={{ height: first * ROW_H }}>
              <td colSpan={span} />
            </tr>
          )}
          {shown.map((r, i) => (
            <tr key={r.row} aria-rowindex={first + i + 2} style={{ height: ROW_H }} className="align-middle">
              <th scope="row" className="num px-3 py-1 font-normal text-ink-600">
                {count(r.row)}
              </th>
              <td className="px-3 py-1">
                <Status row={r} t={t} />
              </td>
              <td className="px-3 py-1">
                <span className="block truncate text-ink-800" title={matchText(r.match, t)}>
                  {matchText(r.match, t)}
                </span>
              </td>
              {columns.map((c) => (
                <td key={c} className="px-3 py-1">
                  <span className="num block truncate text-ink-800" title={r.cells[c] ?? ""}>
                    {r.cells[c] ?? "—"}
                  </span>
                </td>
              ))}
            </tr>
          ))}
          {virtual && last < rows.length && (
            <tr aria-hidden="true" style={{ height: (rows.length - last) * ROW_H }}>
              <td colSpan={span} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
