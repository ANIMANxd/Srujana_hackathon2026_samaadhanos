"use client";

// Per-invoice reads for a customer profile: each case's latest engine
// evaluation (acceptance date, interest, the buyer's three cost lines) and its
// audit events. The profile itself does not carry these yet (CR-18), so they
// come from the existing v1.1 case routes. Live only: the saved v1.1 samples
// are a different invoice and are never shown as this customer's.

import { useEffect, useState } from "react";
import { getCase, getEvents, type Source } from "./api";
import type { AuditEvent, CaseDetail } from "./types";

export type CaseExtra = { detail: CaseDetail | null; events: AuditEvent[] };

export function useCustomerCases(caseIds: string[], source: Source | null): Map<string, CaseExtra> | null {
  const [state, setState] = useState<{ key: string; map: Map<string, CaseExtra> } | null>(null);
  const key = `${source}:${caseIds.join(",")}`;

  useEffect(() => {
    if (source !== "live") return;
    let alive = true;
    Promise.all(
      caseIds.map(async (id): Promise<[string, CaseExtra]> => {
        const [d, e] = await Promise.allSettled([getCase(id), getEvents(id)]);
        return [
          id,
          {
            detail: d.status === "fulfilled" && d.value.source === "live" ? d.value.data : null,
            events: e.status === "fulfilled" && e.value.source === "live" ? e.value.data : [],
          },
        ];
      }),
    ).then((pairs) => {
      if (alive) setState({ key, map: new Map(pairs) });
    });
    return () => {
      alive = false;
    };
    // `key` names the request; the id array is a fresh value each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (source === "offline") return new Map();
  return state?.key === key ? state.map : null;
}
