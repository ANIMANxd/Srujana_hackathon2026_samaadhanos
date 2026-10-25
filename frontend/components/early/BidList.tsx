"use client";

import { useState } from "react";
import { selectBid } from "@/lib/api";
import { toPaise } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Bid } from "@/lib/types";
import { BidCard } from "./BidCard";

/** What you receive, highest first. A bid whose amount cannot be read goes last. Order only; no figure is computed. */
function byYouReceive(a: Bid, b: Bid): number {
  const x = toPaise(a.net_amount);
  const y = toPaise(b.net_amount);
  if (x === null && y === null) return 0;
  if (x === null) return 1;
  if (y === null) return -1;
  return x === y ? 0 : x > y ? -1 : 1;
}

/**
 * The bids as the server lists them, sorted by what you receive. Selecting one
 * calls POST /financing/bids/{id}/select; the screen then waits for the server
 * to say AWAITING_ESIGN rather than moving on by itself. While one selection is
 * in flight the others are off, and the button itself ignores a second click.
 */
export function BidList({
  caseId,
  bids,
  version,
  offline,
  onConflict,
  onSelected,
}: {
  caseId: string;
  bids: Bid[];
  version: number | null;
  offline: boolean;
  onConflict: () => Promise<void> | void;
  onSelected: () => Promise<void> | void;
}) {
  const { t } = useT();
  const [selecting, setSelecting] = useState<string | null>(null);
  const sorted = [...bids].sort(byYouReceive);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-600">{t("early.bid.intro")}</p>
      <ul className="flex flex-col gap-3">
        {sorted.map((bid) => (
          <BidCard
            key={bid.id}
            bid={bid}
            version={version}
            offline={offline}
            onConflict={onConflict}
            disabled={selecting !== null && selecting !== bid.id}
            onSelect={async (opts) => {
              setSelecting(bid.id);
              try {
                await selectBid(caseId, bid.id, opts);
                await onSelected();
              } finally {
                setSelecting(null);
              }
            }}
          />
        ))}
      </ul>
    </div>
  );
}
