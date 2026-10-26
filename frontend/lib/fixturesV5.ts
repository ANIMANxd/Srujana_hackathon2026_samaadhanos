// Offline samples for contract v1.2 (customer book), synced from
// ../contracts/fixtures/v5. Each file is {_fixture, payload}; only the payload
// is used, plus the `_fixture.placeholder` flag so the screen can label hand-
// shaped figures "placeholder" (golden rule 7). Nothing here is computed in the
// browser: rows, totals and averages are copied as the file has them.

import { RAW_V5 } from "@/fixtures";
import type { CustomerSort, SortDir } from "./api";
import { toPaise } from "./format";
import type {
  CustomerGroupRow,
  CustomerProfile,
  CustomerRow,
  ImportPreview,
  ImportResult,
  Payment,
  PortfolioInsights,
  Suggestion,
} from "./types";

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function payload(name: string): unknown {
  const f = RAW_V5[name];
  return isObject(f) && "payload" in f ? f.payload : null;
}

/** True while any bundled v1.2 sample is still hand-shaped rather than exported from the seeded DB. */
export const V5_FIXTURES_PLACEHOLDER: boolean = Object.values(RAW_V5).some(
  (f) => isObject(f) && isObject(f._fixture) && f._fixture.placeholder === true,
);

function asRow(v: unknown): CustomerRow | null {
  return isObject(v) && typeof v.id === "string" && typeof v.display_name === "string" ? (v as unknown as CustomerRow) : null;
}

function asGroup(v: unknown): CustomerGroupRow | null {
  return isObject(v) && typeof v.id === "string" && typeof v.label === "string" ? (v as unknown as CustomerGroupRow) : null;
}

/** The sample groups (one today). */
export function offlineCustomerGroups(): CustomerGroupRow[] | null {
  const g = asGroup(payload("customer-group-row"));
  return g ? [g] : null;
}

/** Every sample customer row: the standalone row plus the sample group's members, each once, in file order. */
export function offlineCustomerRows(): CustomerRow[] | null {
  const rows: CustomerRow[] = [];
  const seen = new Set<string>();
  const add = (r: CustomerRow | null) => {
    if (r && !seen.has(r.id)) {
      seen.add(r.id);
      rows.push(r);
    }
  };
  add(asRow(payload("customer-row")));
  for (const g of offlineCustomerGroups() ?? []) for (const m of g.members ?? []) add(asRow(m));
  return rows.length ? rows : null;
}

/**
 * Order the sample rows the way the server would, so sorting can be shown
 * offline. Money strings are compared as exact paise (an ordering, not a sum);
 * rows the key cannot place (no figure, or a key the rows do not carry such as
 * the profile's average days) keep file order at the end.
 */
export function sortSampleRows(rows: CustomerRow[], sort: CustomerSort, dir: SortDir): CustomerRow[] {
  const sign = dir === "asc" ? 1 : -1;
  const keyOf = (r: CustomerRow): bigint | number | string | null => {
    switch (sort) {
      case "outstanding_total":
      case "overdue_total":
        return toPaise(r[sort]);
      case "oldest_overdue_days":
        return r.oldest_overdue_days ?? null;
      case "last_payment_on":
        return r.last_payment_on ?? null;
      case "display_name":
        return r.display_name.toLocaleLowerCase();
      default:
        return null;
    }
  };
  const indexed = rows.map((r, i) => ({ r, i, k: keyOf(r) }));
  indexed.sort((a, b) => {
    if (a.k === null || b.k === null) return a.k === b.k ? a.i - b.i : a.k === null ? 1 : -1;
    if (a.k === b.k) return a.i - b.i;
    return (a.k < b.k ? -1 : 1) * sign;
  });
  return indexed.map((x) => x.r);
}

/** The one sample profile. It stands in for whichever customer was asked for, and is labelled a sample. */
export function offlineCustomerProfile(): CustomerProfile | null {
  const p = payload("customer-profile");
  return isObject(p) && isObject(p.customer) && isObject(p.stats) ? (p as unknown as CustomerProfile) : null;
}

export function offlineSuggestions(): Suggestion[] | null {
  const s = payload("suggestion");
  return isObject(s) && typeof s.kind === "string" ? [s as unknown as Suggestion] : null;
}

export function offlinePayments(): Payment[] | null {
  const p = payload("payment");
  return isObject(p) && typeof p.id === "string" ? [p as unknown as Payment] : null;
}

export function offlinePortfolioInsights(): PortfolioInsights | null {
  const p = payload("portfolio-insights");
  return isObject(p) && typeof p.as_of === "string" ? (p as unknown as PortfolioInsights) : null;
}

/** Import samples are for screen layout only; an offline import is never run. */
export function sampleImportPreview(): ImportPreview | null {
  const p = payload("import-preview");
  return isObject(p) && typeof p.preview_id === "string" ? (p as unknown as ImportPreview) : null;
}

export function sampleImportResult(): ImportResult | null {
  const p = payload("import-result");
  return isObject(p) && typeof p.preview_id === "string" ? (p as unknown as ImportResult) : null;
}
