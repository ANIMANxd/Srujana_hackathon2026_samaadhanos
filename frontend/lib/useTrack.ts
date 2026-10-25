"use client";

// A stored case and its active track (contract v1.1). Loads GET /cases/{id},
// then keeps it fresh: server-sent events from /cases/{id}/stream when the
// browser and server allow it, otherwise a 3 second poll. Any stream message
// just triggers a re-read, so the screen always shows what the server stores
// and never a half-applied event. When the backend is unreachable it shows a
// saved sample case, labelled offline, and keeps retrying quietly.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getCase, streamUrl, type Source, type Sourced } from "./api";
import type { CaseDetail, Track } from "./types";

export type TrackStatus = "idle" | "loading" | "ready" | "not_found" | "error";

/** How updates arrive: pushed over the stream, polled, or not at all (offline retry only). */
export type LiveMode = "stream" | "polling" | "off";

export type TrackView = {
  caseDetail: CaseDetail | null;
  track: Track | null;
  /** The track version to send as If-Match; null when there is no active track. */
  version: number | null;
  source: Source | null;
  status: TrackStatus;
  error: string | null;
  live: LiveMode;
  refresh: () => Promise<void>;
};

const POLL_MS = 3000;
const OFFLINE_RETRY_MS = 10_000;
const STREAM_RETRY_MS = 15_000;
// A stream can be open yet silent (a proxy that buffers events), so a slow poll runs alongside it.
const STREAM_SAFETY_MS = 10_000;

/**
 * `enabled` false keeps the hook inert (stateless preset and legacy cases).
 * `offlineState` chooses which saved sample case stands in while offline.
 */
export function useTrack(caseId: string, enabled: boolean, offlineState?: string | null): TrackView {
  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [rawStatus, setStatus] = useState<TrackStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [liveMode, setLive] = useState<LiveMode>("polling");
  const seq = useRef(0);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const apply = useCallback((mine: number, res: Sourced<CaseDetail>) => {
    // A slower, older answer must not overwrite a newer one.
    if (!alive.current || mine !== seq.current) return;
    // Keep the old object when nothing changed, so a quiet poll does not re-render the screen.
    setCaseDetail((prev) => (prev && JSON.stringify(prev) === JSON.stringify(res.data) ? prev : res.data));
    setSource(res.source);
    setStatus("ready");
    setError(null);
  }, []);

  const fail = useCallback((mine: number, e: unknown) => {
    if (!alive.current || mine !== seq.current) return;
    if (e instanceof ApiError && e.status === 404) {
      setStatus("not_found");
      return;
    }
    setError(e instanceof Error ? e.message : "The case could not be loaded.");
    // Keep what is on screen; only a first load with nothing to show is an error.
    setStatus((s) => (s === "ready" ? "ready" : "error"));
  }, []);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    const mine = ++seq.current;
    try {
      apply(mine, await getCase(caseId, offlineState));
    } catch (e) {
      fail(mine, e);
    }
  }, [caseId, enabled, offlineState, apply, fail]);

  // First load. The hook is mounted per case (the page keys on the id), so there is no stale data to clear.
  useEffect(() => {
    if (!enabled) return;
    const mine = ++seq.current;
    getCase(caseId, offlineState).then((res) => apply(mine, res), (e) => fail(mine, e));
  }, [enabled, caseId, offlineState, apply, fail]);

  const status: TrackStatus = enabled && rawStatus === "idle" ? "loading" : rawStatus;

  // Keep it fresh: stream when live, poll as the fallback, slow retry when offline.
  const started = status === "ready" || status === "error";
  useEffect(() => {
    if (!enabled || !started) return;
    let stopped = false;
    let es: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const stopPolling = () => {
      if (poll) clearInterval(poll);
      poll = null;
    };
    const startPolling = (ms: number) => {
      stopPolling();
      poll = setInterval(refresh, ms);
    };

    if (source === "offline") {
      startPolling(OFFLINE_RETRY_MS);
    } else {
      const connect = () => {
        if (stopped) return;
        if (typeof EventSource === "undefined") return; // polling already runs
        es = new EventSource(streamUrl(caseId));
        es.onopen = () => {
          startPolling(STREAM_SAFETY_MS);
          setLive("stream");
        };
        es.onmessage = () => {
          refresh();
        };
        es.onerror = () => {
          // The browser would retry on its own, but a quiet poll keeps the
          // screen current meanwhile; a fresh connection is tried later.
          es?.close();
          es = null;
          setLive("polling");
          startPolling(POLL_MS);
          retry = setTimeout(connect, STREAM_RETRY_MS);
        };
      };
      // Poll until the stream proves itself open.
      startPolling(POLL_MS);
      connect();
    }

    return () => {
      stopped = true;
      es?.close();
      stopPolling();
      if (retry) clearTimeout(retry);
    };
  }, [enabled, started, source, caseId, refresh]);

  const track = caseDetail?.active_track ?? null;
  const live: LiveMode = source === "offline" ? "off" : liveMode;
  return { caseDetail, track, version: track?.version ?? null, source, status, error, live, refresh };
}
