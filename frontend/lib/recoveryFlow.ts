// Display derivation for the recovery ladder. The server's track.state says what
// was prepared and what the owner confirmed as sent; this file only reads it.

import type { Stage, Track } from "./types";

export type RecoveryStatus = "none" | "prepared" | "sent";

const ORDER = [
  "NEW",
  "STAGE_1_PREPARED",
  "STAGE_1_SENT_BY_OWNER",
  "STAGE_2_PREPARED",
  "STAGE_2_SENT_BY_OWNER",
  "STAGE_3_PREPARED",
  "STAGE_3_SENT_BY_OWNER",
  "STAGE_4_PACK_READY",
  "ODR_FILED_BY_OWNER",
];

/** Position of a recovery state on the ladder; the end states (paid, settled, closed) count as past everything. */
function rank(state: string): number {
  const i = ORDER.indexOf(state);
  if (i >= 0) return i;
  return state === "PAID" || state === "SETTLED" || state === "CLOSED" ? ORDER.length : -1;
}

/** What the server says about one stage of the ladder; "none" without a recovery track. */
export function recoveryStatus(track: Track | null, stage: Stage): RecoveryStatus {
  if (!track || track.kind !== "RECOVERY") return "none";
  const at = rank(track.state);
  if (stage === 4) return at >= rank("ODR_FILED_BY_OWNER") ? "sent" : at >= rank("STAGE_4_PACK_READY") ? "prepared" : "none";
  if (at >= rank(`STAGE_${stage}_SENT_BY_OWNER`)) return "sent";
  if (at >= rank(`STAGE_${stage}_PREPARED`)) return "prepared";
  return "none";
}

/** Prepared and waiting for the owner to say they sent it: the one stage "I've sent it" applies to. */
export function awaitingSent(track: Track | null, stage: Stage): boolean {
  return track?.kind === "RECOVERY" && track.state === `STAGE_${stage}_PREPARED`;
}

/** After signing the receivable belongs to the financier (state-machines.md section 3): recovery is off. */
const LOCKING = new Set([
  "AWAITING_ESIGN",
  "AWAITING_DISBURSEMENT",
  "DISBURSED",
  "DISBURSEMENT_FAILED",
  "SETTLED",
  "SETTLED_WITHOUT_RECOURSE",
]);

export function financingLocksRecovery(track: Track | null): boolean {
  return track?.kind === "FINANCING" && LOCKING.has(track.state);
}

/**
 * Whether to offer "Prepare": no track yet, recovery already running, or the
 * server says it can switch over. The server still has the last word.
 */
export function canPrepare(track: Track | null, actions: string[]): boolean {
  return !track || track.kind === "RECOVERY" || actions.includes("switch_to_recovery");
}
