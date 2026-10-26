"use client";

// Shared plumbing for the customer-book hooks (contract v1.2): one read that
// stays current (focus, visibility, a cross-tab "the book changed" message, a
// slow backstop timer), and the action ids that name each mutation for
// IdempotentButton. Copy comes from lib/i18n; errors are i18n keys plus the
// server's own plain-English message when it sent one.

import { useCallback, useEffect, useState } from "react";
import { ApiError, BackendUnreachable, type Source, type Sourced } from "./api";
import { V5_FIXTURES_PLACEHOLDER } from "./fixturesV5";
import type { MessageKey } from "./i18n/en";
import type { PaymentInput } from "./api";

const CHANNEL = "samaadhan-customers";
const BACKSTOP_MS = 15_000;

/** Tell every open customer screen (this tab or another) to re-read after a mutation. */
export function announceBookChange(): void {
  try {
    const ch = new BroadcastChannel(CHANNEL);
    ch.postMessage({ at: Date.now() });
    ch.close();
  } catch {
    /* no BroadcastChannel: focus and the timer still refresh */
  }
}

export type ReadError = { key: MessageKey; detail: string | null };

export type BookRead<T> = {
  data: T | null;
  source: Source | null;
  /** Offline and the bundled sample is hand-shaped: label its figures "placeholder". */
  placeholder: boolean;
  error: ReadError | null;
  loading: boolean;
  refresh: () => void;
};

/** One kept-current read. `key` names the request (its query); a new key re-reads at once. */
export function useBookRead<T>(key: string, enabled: boolean, fetcher: () => Promise<Sourced<T>>, failKey: MessageKey): BookRead<T> {
  const [ok, setOk] = useState<{ key: string; data: T; source: Source } | null>(null);
  const [bad, setBad] = useState<{ key: string; error: ReadError } | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    fetcher().then(
      (r) => {
        if (!alive) return;
        // Keep the old object when nothing changed, so a quiet re-read does not re-render.
        setOk((prev) =>
          prev && prev.key === key && prev.source === r.source && JSON.stringify(prev.data) === JSON.stringify(r.data)
            ? prev
            : { key, data: r.data, source: r.source },
        );
        setBad(null);
      },
      (e: unknown) => {
        if (!alive) return;
        const error: ReadError =
          e instanceof BackendUnreachable
            ? { key: "book.unreachable", detail: null }
            : { key: failKey, detail: e instanceof ApiError ? e.message : null };
        setBad({ key, error });
      },
    );
    return () => {
      alive = false;
    };
    // The fetcher is a fresh closure each render; `key` is what names the read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, tick]);

  useEffect(() => {
    if (!enabled) return;
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
  }, [enabled, refresh]);

  const current = ok?.key === key ? ok : null;
  const failed = bad?.key === key ? bad.error : null;
  return {
    // The last answer stays on screen while a new query loads.
    data: ok?.data ?? null,
    source: ok?.source ?? null,
    placeholder: ok?.source === "offline" && V5_FIXTURES_PLACEHOLDER,
    error: failed,
    loading: enabled && !current && !failed,
    refresh,
  };
}

/**
 * Action ids for IdempotentButton: each names the action AND its payload, so a
 * retried click reuses its key and a different body gets a new one.
 */
export const bookAction = {
  attachGstin: (customerId: string, gstin: string) => `customer.gstin.attach:${customerId}:${gstin}`,
  detachGstin: (customerId: string, gstin: string) => `customer.gstin.detach:${customerId}:${gstin}`,
  attachCustomer: (targetId: string, sourceId: string) => `customer.attach:${targetId}:${sourceId}`,
  detachCustomer: (targetId: string, sourceId: string) => `customer.detach:${targetId}:${sourceId}`,
  createGroup: (label: string, customerIds: string[]) => `group.create:${label}:${[...customerIds].sort().join(",")}`,
  linkToGroup: (groupId: string, customerId: string) => `group.link:${groupId}:${customerId}`,
  unlinkFromGroup: (groupId: string, customerId: string) => `group.unlink:${groupId}:${customerId}`,
  dismissSuggestion: (a: string, b: string) => `suggestion.dismiss:${[a, b].sort().join(":")}`,
  undoDismissSuggestion: (a: string, b: string) => `suggestion.undo:${[a, b].sort().join(":")}`,
  recordPayment: (caseId: string, p: PaymentInput) => `payment.record:${caseId}:${p.amount}:${p.paid_on}:${p.method}:${p.note ?? ""}`,
  voidPayment: (caseId: string, paymentId: string) => `payment.void:${caseId}:${paymentId}`,
  previewImport: (filename: string, size: number, lastModified: number) => `import.preview:${filename}:${size}:${lastModified}`,
  confirmImport: (previewId: string) => `import.confirm:${previewId}`,
} as const;
