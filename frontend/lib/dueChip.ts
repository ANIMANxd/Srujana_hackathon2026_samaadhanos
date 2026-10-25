// Which words and look a Dues row's track chip gets. Reads the server's track
// (kind + state) and picks a label; it never decides what may happen next.

import type { Tone } from "./derive";
import type { Vars } from "./i18n";
import type { MessageKey } from "./i18n/en";
import type { Track } from "./types";
import type { IconName } from "@/components/common/Icon";

export type Chip = {
  /** "Get paid early" / "Recover"; null for "Choose an option". */
  prefix: MessageKey | null;
  status: MessageKey;
  vars?: Vars;
  tone: Tone;
  icon: IconName;
};

const FIN: Record<string, { tone: Tone; icon: IconName }> = {
  NEW: { tone: "info", icon: "clock" },
  FINANCEABLE: { tone: "info", icon: "ok" },
  NOT_FINANCEABLE: { tone: "warn", icon: "block" },
  AWAITING_BUYER_ACCEPTANCE: { tone: "info", icon: "clock" },
  BIDDING_OPEN: { tone: "info", icon: "clock" },
  BIDS_AVAILABLE: { tone: "info", icon: "ok" },
  NO_BIDS: { tone: "warn", icon: "block" },
  AWAITING_ESIGN: { tone: "info", icon: "doc" },
  AWAITING_DISBURSEMENT: { tone: "info", icon: "clock" },
  DISBURSED: { tone: "ok", icon: "ok" },
  DISBURSEMENT_FAILED: { tone: "warn", icon: "warn" },
  SETTLED: { tone: "ok", icon: "ok" },
  SETTLED_WITHOUT_RECOURSE: { tone: "ok", icon: "ok" },
  BUYER_DECLINED: { tone: "warn", icon: "block" },
  CANCELLED: { tone: "info", icon: "block" },
};

const REC_END = new Set(["PAID", "SETTLED", "CLOSED", "NEW"]);

export function trackChip(track: Track | null | undefined): Chip {
  if (!track) return { prefix: null, status: "dues.chip.choose", tone: "info", icon: "open" };
  if (track.kind === "FINANCING") {
    const look = FIN[track.state] ?? { tone: "info" as const, icon: "clock" as const };
    return { prefix: "dues.chip.early", status: `dues.chip.fin.${track.state}` as MessageKey, ...look };
  }
  const m = /^STAGE_(\d)_(PREPARED|SENT_BY_OWNER)$/.exec(track.state);
  if (m) {
    const sent = m[2] === "SENT_BY_OWNER";
    return {
      prefix: "dues.chip.recover",
      status: sent ? "dues.chip.rec.sent" : "dues.chip.rec.prepared",
      vars: { n: m[1] },
      tone: sent ? "ok" : "info",
      icon: sent ? "ok" : "doc",
    };
  }
  if (track.state === "STAGE_4_PACK_READY") return { prefix: "dues.chip.recover", status: "dues.chip.rec.pack", tone: "info", icon: "doc" };
  if (track.state === "ODR_FILED_BY_OWNER") return { prefix: "dues.chip.recover", status: "dues.chip.rec.odr", tone: "ok", icon: "ok" };
  if (REC_END.has(track.state)) {
    return { prefix: "dues.chip.recover", status: `dues.chip.rec.${track.state}` as MessageKey, tone: track.state === "PAID" ? "ok" : "info", icon: "ok" };
  }
  return { prefix: "dues.chip.recover", status: "dues.chip.rec.NEW", tone: "info", icon: "clock" };
}

/** Money already received through Option 1 (simulated). */
export function paidEarly(track: Track | null | undefined): boolean {
  return (
    track?.kind === "FINANCING" &&
    (track.state === "DISBURSED" || track.state === "SETTLED" || track.state === "SETTLED_WITHOUT_RECOURSE")
  );
}
