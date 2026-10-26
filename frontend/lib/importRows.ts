// What the CSV preview tells us about each row. The v1.2 contract carries
// counts, a few sample rows and loose message lists; the per-row status and the
// customer match are additive fields the server does not send yet (CR-20). They
// are read defensively here by name: with them the table shows every row's
// status and match, without them it shows the sample rows as "not checked" and
// never invents a status.

import type { ImportPreview, ImportResult } from "./types";

export type RowStatus = "ready" | "warning" | "error" | "unchecked";

export type RowMatch =
  | { kind: "existing"; name: string | null; customerId: string | null }
  | { kind: "new" }
  | { kind: "provisional" }
  | { kind: "unknown" };

export type ImportRowView = {
  /** 1-based row number in the file, as the server counts it. */
  row: number;
  status: RowStatus;
  message: string | null;
  match: RowMatch;
  cells: Record<string, string>;
};

export type PreviewView = {
  rows: ImportRowView[];
  columns: string[];
  /** True when the server sent a status for every row it listed. */
  checked: boolean;
  /** Rows the server flagged as needing a look, when it said so per row. */
  warningRows: number | null;
};

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);

function parseStatus(v: unknown): RowStatus {
  const s = typeof v === "string" ? v.toLowerCase() : "";
  if (s === "ready" || s === "ok" || s === "valid") return "ready";
  if (s === "warning" || s === "warn") return "warning";
  if (s === "error" || s === "invalid") return "error";
  return "unchecked";
}

function parseMatch(v: unknown): RowMatch {
  if (!isObject(v)) return { kind: "unknown" };
  const kind = typeof v.kind === "string" ? v.kind.toLowerCase() : "";
  if (kind === "existing") return { kind: "existing", name: str(v.customer_name) ?? str(v.name), customerId: str(v.customer_id) };
  if (kind === "new") return { kind: "new" };
  if (kind === "provisional") return { kind: "provisional" };
  return { kind: "unknown" };
}

function cellsOf(v: unknown): Record<string, string> {
  if (!isObject(v)) return {};
  return Object.fromEntries(Object.entries(v).filter((e): e is [string, string] => typeof e[1] === "string"));
}

export function previewView(p: ImportPreview): PreviewView {
  const extra = (p as unknown as Record<string, unknown>).rows;
  const columns = p.columns ?? [];
  if (Array.isArray(extra) && extra.length > 0) {
    const rows = extra.map((r, i): ImportRowView => {
      const o = isObject(r) ? r : {};
      return {
        row: typeof o.row === "number" ? o.row : i + 1,
        status: parseStatus(o.status),
        message: str(o.message),
        match: parseMatch(o.match ?? o.customer_match),
        cells: cellsOf(o.cells ?? o.values ?? o),
      };
    });
    return { rows, columns, checked: rows.every((r) => r.status !== "unchecked"), warningRows: rows.filter((r) => r.status === "warning").length };
  }
  const rows = (p.sample_rows ?? []).map((cells, i): ImportRowView => ({ row: i + 1, status: "unchecked", message: null, match: { kind: "unknown" }, cells }));
  return { rows, columns, checked: false, warningRows: null };
}

/** Customer ids the result names, when the server sends them (CR-20). */
export function resultCustomerIds(r: ImportResult): string[] {
  const raw = (r as unknown as Record<string, unknown>).customer_ids;
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
}

/** The columns the sample file starts with (placeholder until the server publishes its own, CR-20). */
export const TEMPLATE_COLUMNS = ["buyer_name", "buyer_gstin", "invoice_no", "invoice_date", "amount"] as const;

export function templateCsv(): string {
  return `${TEMPLATE_COLUMNS.join(",")}\r\n`;
}
