"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Wall-clock time in `stepMs` steps. 0 on the server, so nothing time-based renders until the browser has the time. */
export function useNow(stepMs = 30_000): number {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const id = setInterval(onChange, stepMs);
      return () => clearInterval(id);
    },
    [stepMs],
  );
  return useSyncExternalStore(
    subscribe,
    () => Math.floor(Date.now() / stepMs) * stepMs,
    () => 0,
  );
}

/** "23h 41m", "12m" or, with `seconds`, "9m 41s". Display only: the server decides what has expired. */
export function timeLeft(until: string, now: number, seconds = false): { text: string; expired: boolean } | null {
  if (now === 0) return null;
  const ms = Date.parse(until) - now;
  if (Number.isNaN(ms)) return null;
  if (ms <= 0) return { text: "", expired: true };
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (seconds) return { text: h > 0 ? `${h}h ${m}m` : `${m}m ${String(s).padStart(2, "0")}s`, expired: false };
  return { text: h > 0 ? `${h}h ${m}m` : `${Math.max(m, 1)}m`, expired: false };
}
