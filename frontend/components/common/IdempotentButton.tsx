"use client";

// A button for one server-side action (contract v1.1). It disables itself on
// click, sends a fresh Idempotency-Key (reused only when the same action is
// retried after a dropped connection) and the track version as If-Match. A 409
// means another tab got there first: it refreshes and says so, never retries.

import { useRef, useState, type ReactNode } from "react";
import { ApiError, BackendUnreachable, type MutationOptions } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { idempotencyKeyFor, releaseIdempotencyKey } from "@/lib/idempotency";

type Notice = "conflict" | "unreachable" | "failed";

export function IdempotentButton({
  actionId,
  run,
  version,
  onConflict,
  onDone,
  offline = false,
  disabled = false,
  className = "btn btn-primary",
  children,
}: {
  /** Names this action and its payload; a different body needs a different id. */
  actionId: string;
  run: (opts: MutationOptions) => Promise<void>;
  /** Track version sent as If-Match; omit for actions with no track yet. */
  version?: number | null;
  /** Called on 409 to re-read the case (the `refresh` from useTrack). */
  onConflict: () => Promise<void> | void;
  onDone?: () => void;
  /** Mutations are off while only a saved sample is on screen. */
  offline?: boolean;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const { t } = useT();
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  // State updates lag a fast double click; a ref blocks the second one.
  const busy = useRef(false);

  async function click() {
    if (busy.current || offline || disabled) return;
    busy.current = true;
    setPending(true);
    setNotice(null);
    const opts: MutationOptions = { idempotencyKey: idempotencyKeyFor(actionId) };
    // No track yet is `If-Match: 0` (the server treats it as "create"); a missing header is a 400.
    if (version !== undefined) opts.ifMatch = version ?? 0;
    try {
      await run(opts);
      releaseIdempotencyKey(actionId);
      onDone?.();
    } catch (e) {
      if (e instanceof BackendUnreachable) {
        // Same action, same key: the server replays if the first try did land.
        setNotice("unreachable");
      } else if (e instanceof ApiError && e.status === 409) {
        releaseIdempotencyKey(actionId);
        setNotice("conflict");
        await onConflict();
      } else {
        releaseIdempotencyKey(actionId);
        setNotice("failed");
      }
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  const offlineId = `${actionId}:offline`;
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        className={className}
        disabled={pending || offline || disabled}
        aria-busy={pending}
        aria-describedby={offline ? offlineId : undefined}
        onClick={click}
      >
        {children}
      </button>
      {offline && (
        <span id={offlineId} className="text-xs text-ink-500">
          {t("action.offline_disabled")}
        </span>
      )}
      <span role="status" className="text-xs text-ink-600">
        {notice === "conflict" && t("action.conflict")}
        {notice === "unreachable" && t("action.unreachable")}
        {notice === "failed" && t("action.failed")}
      </span>
    </span>
  );
}
