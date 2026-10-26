"use client";

// A short-lived "done, undo?" notice. It stays 10 seconds, waits while the
// pointer or keyboard focus is on it, and says plainly when the undo worked or
// failed. The hook owns the clock so the toast can move (inside the open drawer,
// or on the page once the drawer closes) without losing its place.

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BackendUnreachable } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { undoChange, type ReviewChange } from "@/lib/reviewLog";
import { Icon } from "../common/Icon";

export const UNDO_MS = 10_000;

type Shown = { change: ReviewChange; message: string; phase: "ready" | "busy" | "undone" | "failed" | "offline" };

export type UndoToastState = {
  shown: Shown | null;
  show: (change: ReviewChange, message: string) => void;
  undo: () => void;
  close: () => void;
  hold: (on: boolean) => void;
};

export function useUndoToast(onUndone?: () => void): UndoToastState {
  const [shown, setShown] = useState<Shown | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const holding = useRef(false);
  const doneRef = useRef(onUndone);
  useEffect(() => {
    doneRef.current = onUndone;
  }, [onUndone]);

  const stop = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);
  const close = useCallback(() => {
    stop();
    setShown(null);
  }, [stop]);
  const arm = useCallback(
    (ms: number) => {
      stop();
      timer.current = setTimeout(close, ms);
    },
    [stop, close],
  );

  useEffect(() => stop, [stop]);

  const show = useCallback(
    (change: ReviewChange, message: string) => {
      setShown({ change, message, phase: "ready" });
      if (!holding.current) arm(UNDO_MS);
    },
    [arm],
  );

  const undo = useCallback(() => {
    if (!shown || shown.phase === "busy") return;
    const { change, message } = shown;
    stop();
    setShown({ change, message, phase: "busy" });
    undoChange(change).then(
      () => {
        setShown({ change, message, phase: "undone" });
        doneRef.current?.();
        arm(4_000);
      },
      (e: unknown) => {
        setShown({ change, message, phase: e instanceof BackendUnreachable ? "offline" : "failed" });
        // Leave the notice up while the owner can still retry; the profile page keeps the option.
        arm(UNDO_MS);
      },
    );
  }, [shown, stop, arm]);

  const hold = useCallback(
    (on: boolean) => {
      holding.current = on;
      if (on) stop();
      else if (shown && shown.phase !== "busy") arm(UNDO_MS);
    },
    [shown, stop, arm],
  );

  return { shown, show, undo, close, hold };
}

const PHASE_NOTE: Partial<Record<Shown["phase"], MessageKey>> = {
  undone: "review.toast.undone",
  failed: "review.toast.failed",
  offline: "review.toast.offline",
};

export function UndoToast({ toast, className = "" }: { toast: UndoToastState; className?: string }): ReactNode {
  const { t } = useT();
  const s = toast.shown;
  if (!s) return null;
  const note = PHASE_NOTE[s.phase];
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-rule bg-ink-950 px-4 py-3 text-sm text-white shadow-float ${className}`}
      onMouseEnter={() => toast.hold(true)}
      onMouseLeave={() => toast.hold(false)}
      onFocus={() => toast.hold(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) toast.hold(false);
      }}
    >
      <p className="min-w-0 flex-1">{note ? t(note) : s.message}</p>
      {s.phase !== "undone" && (
        <button
          type="button"
          onClick={toast.undo}
          disabled={s.phase === "busy"}
          aria-busy={s.phase === "busy"}
          className="rounded-md border border-white/40 px-3 py-1 font-medium hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-60"
        >
          {t("review.undo")}
        </button>
      )}
      <button
        type="button"
        onClick={toast.close}
        aria-label={t("common.close")}
        className="rounded-md p-1 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        <Icon name="close" className="h-4 w-4" />
      </button>
    </div>
  );
}
