"use client";

// One read of a server resource, re-read whenever `key` changes (the screen
// passes the track version, so a state change re-reads it). The last answer
// stays on screen while the next one loads.

import { useEffect, useState } from "react";
import { ApiError, type Source, type Sourced } from "./api";

export type Read<T> = { data: T | null; source: Source | null; error: string | null; loading: boolean };

export function useRead<T>(key: string, enabled: boolean, fetcher: () => Promise<Sourced<T>>): Read<T> {
  const [ok, setOk] = useState<{ key: string; data: T; source: Source } | null>(null);
  const [bad, setBad] = useState<{ key: string; message: string } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetcher().then(
      (r) => {
        if (!cancelled) setOk({ key, data: r.data, source: r.source });
      },
      (e: unknown) => {
        if (!cancelled) setBad({ key, message: e instanceof ApiError ? e.message : "This could not be loaded." });
      },
    );
    return () => {
      cancelled = true;
    };
    // The fetcher is a fresh closure each render; `key` is what names the read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  const settled = ok?.key === key || bad?.key === key;
  return {
    data: ok?.data ?? null,
    source: ok?.source ?? null,
    error: bad?.key === key ? bad.message : null,
    loading: enabled && !settled,
  };
}
