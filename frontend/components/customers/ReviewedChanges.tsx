"use client";

// Changes made from the duplicates review that involve this customer, each with
// its own Undo, so a mistake can be reversed after the toast has gone. The list
// is kept in this browser (lib/reviewLog.ts); the server audits every change.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { changesFor, undoChange, type ReviewChange } from "@/lib/reviewLog";
import { BackendUnreachable } from "@/lib/api";

function Row({ c, offline, onUndone }: { c: ReviewChange; offline: boolean; onUndone: () => void }) {
  const { t } = useT();
  const [state, setState] = useState<"idle" | "busy" | "failed" | "offline">("idle");
  const text =
    c.kind === "ATTACH"
      ? t("review.profile.attach", { source: c.sourceName, target: c.targetName })
      : c.kind === "GROUP"
        ? t("review.profile.group", { label: c.label })
        : t("review.profile.dismiss");

  function undo() {
    if (state === "busy") return;
    setState("busy");
    undoChange(c).then(onUndone, (e: unknown) => setState(e instanceof BackendUnreachable ? "offline" : "failed"));
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2">
      <span className="text-sm text-ink-800">{text}</span>
      <span className="flex items-center gap-3">
        <span role="status" className="text-xs text-ink-600">
          {state === "failed" && t("review.toast.failed")}
          {state === "offline" && t("review.toast.offline")}
        </span>
        <button type="button" className="btn btn-secondary" onClick={undo} disabled={offline || state === "busy"} aria-busy={state === "busy"}>
          {t("review.undo")}
        </button>
      </span>
    </li>
  );
}

export function ReviewedChanges({ customerId, offline, refresh }: { customerId: string; offline: boolean; refresh: () => void }) {
  const { t } = useT();
  const [list, setList] = useState<ReviewChange[]>([]);
  const load = useCallback(() => setList(changesFor(customerId)), [customerId]);
  // Read after mount: the log lives in this browser, so the server render has none.
  useEffect(() => {
    queueMicrotask(load);
  }, [load]);
  if (list.length === 0) return null;
  return (
    <section aria-labelledby="reviewed-title" className="panel flex flex-col gap-1 px-5 py-3">
      <h2 id="reviewed-title" className="text-sm font-semibold text-ink-950">
        {t("review.profile.title")}
      </h2>
      <ul className="divide-y divide-rule">
        {list.map((c) => (
          <Row
            key={c.id}
            c={c}
            offline={offline}
            onUndone={() => {
              load();
              refresh();
            }}
          />
        ))}
      </ul>
    </section>
  );
}
