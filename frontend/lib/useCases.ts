"use client";

// The stored cases for the Dues home (GET /cases), kept current: re-read when
// the window gets focus or the tab becomes visible, when another tab reports
// that a case changed (see `announceCaseChange`, fired by useTrack after a
// stream event or poll changed a case), and on a slow timer as a backstop.

import { useCallback, useEffect, useState } from "react";
import { listCases, type Source } from "./api";
import type { CaseSummary } from "./types";

const CHANNEL = "samaadhan-cases";
const BACKSTOP_MS = 5_000;

/** Tell every open Dues page (this tab or another) that a case's track moved. */
export function announceCaseChange(caseId: string): void {
  try {
    const ch = new BroadcastChannel(CHANNEL);
    ch.postMessage({ caseId });
    ch.close();
  } catch {
    /* no BroadcastChannel: focus and the timer still refresh */
  }
}

export type CasesView = {
  cases: CaseSummary[] | null;
  source: Source | null;
  error: string | null;
  refresh: () => void;
};

export function useCases(): CasesView {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    listCases().then(
      (r) => {
        if (!alive) return;
        // Keep the old array when nothing changed, so a quiet re-read does not re-render the list.
        setCases((prev) => (prev && JSON.stringify(prev) === JSON.stringify(r.data) ? prev : r.data));
        setSource(r.source);
        setError(null);
      },
      (e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "The cases could not be loaded.");
      },
    );
    return () => {
      alive = false;
    };
  }, [tick]);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", onVisible);
    const timer = setInterval(refresh, BACKSTOP_MS);
    let channel: BroadcastChannel | null = null;
    try {
      channel = new BroadcastChannel(CHANNEL);
      channel.onmessage = refresh;
    } catch {
      channel = null;
    }
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", onVisible);
      clearInterval(timer);
      channel?.close();
    };
  }, [refresh]);

  return { cases, source, error, refresh };
}
