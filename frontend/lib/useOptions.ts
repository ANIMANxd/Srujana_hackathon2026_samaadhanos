"use client";

// GET /cases/{id}/options for the choice card. The expected payment date is the
// owner's own assumption: changing it re-queries after a short pause, and the
// previous answer stays on screen meanwhile. Nothing is computed here; the
// server (engine and finance module) returns every figure.

import { useEffect, useState } from "react";
import { ApiError, getOptions, type Source } from "./api";
import type { OptionsResponse } from "./types";

export type OptionsView = {
  options: OptionsResponse | null;
  source: Source | null;
  loading: boolean;
  error: string | null;
};

const DEBOUNCE_MS = 400;

type Loaded = { key: string; options: OptionsResponse; source: Source };
type Failed = { key: string; message: string };

/**
 * `date` null asks for the server's default expected date. `refreshKey` (the
 * track version) re-queries when the case moves. `offlineVariant` picks which
 * saved sample stands in while offline.
 */
export function useOptions(
  caseId: string,
  enabled: boolean,
  date: string | null,
  refreshKey: number | null,
  offlineVariant: string | null,
): OptionsView {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState<Failed | null>(null);
  const key = `${caseId}|${date ?? ""}|${refreshKey ?? ""}|${offlineVariant ?? ""}`;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    // The first read is not an edit: only a changed date waits.
    const timer = setTimeout(
      () => {
        getOptions(caseId, date ?? undefined, offlineVariant).then(
          (r) => {
            if (!cancelled) setLoaded({ key, options: r.data, source: r.source });
          },
          (e: unknown) => {
            if (!cancelled) setFailed({ key, message: e instanceof ApiError ? e.message : "The options could not be loaded." });
          },
        );
      },
      date === null ? 0 : DEBOUNCE_MS,
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [caseId, enabled, date, offlineVariant, key]);

  const settled = loaded?.key === key || failed?.key === key;
  return {
    options: loaded?.options ?? null,
    source: loaded?.source ?? null,
    loading: enabled && !settled,
    error: failed?.key === key ? failed.message : null,
  };
}
