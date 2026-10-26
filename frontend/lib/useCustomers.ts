"use client";

// The customer book list (GET /customers), sorted by the server and optionally
// shown in the owner's groups. Grouping only arranges rows the server sent: no
// subtotal is added up here (golden rule 6), and a group never merges legal
// entities, each row stays its own customer with its own cases.

import { useMemo } from "react";
import { listCustomers, type CustomerBook, type CustomerSort, type SortDir } from "./api";
import { useBookRead, type BookRead } from "./customerBook";
import type { CustomerGroupRow, CustomerRow } from "./types";

export type CustomerSection =
  | { kind: "group"; group: CustomerGroupRow; rows: CustomerRow[] }
  | { kind: "ungrouped"; rows: CustomerRow[] };

export type CustomersView = Omit<BookRead<CustomerBook>, "data"> & {
  rows: CustomerRow[] | null;
  groups: CustomerGroupRow[];
  /** Grouped view: one section per group in the order its first row appears, then the rest. Flat view: one section. */
  sections: CustomerSection[] | null;
};

/** Group rows by `group_id`, keeping the server's sort order inside and across sections. */
export function sectionRows(rows: CustomerRow[], groups: CustomerGroupRow[], grouped: boolean): CustomerSection[] {
  if (!grouped) return [{ kind: "ungrouped", rows }];
  const byId = new Map(groups.map((g) => [g.id, g]));
  // Membership from either side: the row's `group_id`, else the group's own `members` list.
  const memberOf = new Map<string, string>();
  for (const g of groups) for (const m of g.members ?? []) memberOf.set(m.id, g.id);
  const sections = new Map<string, CustomerSection & { kind: "group" }>();
  const rest: CustomerRow[] = [];
  for (const r of rows) {
    const groupId = r.group_id ?? memberOf.get(r.id) ?? null;
    if (!groupId) {
      rest.push(r);
      continue;
    }
    let s = sections.get(groupId);
    if (!s) {
      // A row can name a group the list did not send; show it under the row's own label.
      const group: CustomerGroupRow = byId.get(groupId) ?? {
        id: groupId,
        label: r.group_label ?? groupId,
        created_at: "",
        created_by: "",
        member_count: 0,
      };
      s = { kind: "group", group, rows: [] };
      sections.set(groupId, s);
    }
    s.rows.push(r);
  }
  const out: CustomerSection[] = [...sections.values()];
  if (rest.length) out.push({ kind: "ungrouped", rows: rest });
  return out;
}

export function useCustomers({ sort, dir, grouped }: { sort: CustomerSort; dir: SortDir; grouped: boolean }): CustomersView {
  const read = useBookRead(`customers:${sort}:${dir}`, true, () => listCustomers({ sort, dir }), "customers.load_failed");
  const book = read.data;
  const sections = useMemo(() => (book ? sectionRows(book.customers, book.groups, grouped) : null), [book, grouped]);
  return {
    source: read.source,
    placeholder: read.placeholder,
    error: read.error,
    loading: read.loading,
    refresh: read.refresh,
    rows: book?.customers ?? null,
    groups: book?.groups ?? [],
    sections,
  };
}
