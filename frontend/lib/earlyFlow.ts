// Display derivation for the Get-paid-early stepper. The server's track.state is
// the only input; nothing here decides what may happen next (that is the
// server's `available_actions`), and nothing advances on its own.

import type { TrackState } from "./types";

export const EARLY_STEPS = ["check", "ask", "bid", "sign", "money", "done"] as const;
export type EarlyStep = (typeof EARLY_STEPS)[number];

/** States where this route is not going ahead. */
export type Failure = "NOT_FINANCEABLE" | "BUYER_DECLINED" | "NO_BIDS" | "CANCELLED" | "DISBURSEMENT_FAILED";

export type EarlyView = {
  /** The step the server says is happening now; null when the route ended. */
  current: EarlyStep | null;
  failure: Failure | null;
  /** The step where it stopped, so earlier steps still read as done. */
  stoppedAt: EarlyStep | null;
  /** Money received or settled. */
  finished: boolean;
};

const AT: Partial<Record<TrackState, EarlyStep>> = {
  NEW: "check",
  FINANCEABLE: "ask",
  AWAITING_BUYER_ACCEPTANCE: "ask",
  BIDDING_OPEN: "bid",
  BIDS_AVAILABLE: "bid",
  AWAITING_ESIGN: "sign",
  AWAITING_DISBURSEMENT: "money",
  DISBURSED: "done",
  SETTLED: "done",
  SETTLED_WITHOUT_RECOURSE: "done",
};

const FAILED_AT: Record<Failure, EarlyStep | null> = {
  NOT_FINANCEABLE: "check",
  BUYER_DECLINED: "ask",
  NO_BIDS: "bid",
  CANCELLED: null,
  DISBURSEMENT_FAILED: "money",
};

function isFailure(state: TrackState): state is Failure {
  return state in FAILED_AT;
}

export function earlyView(state: TrackState | null): EarlyView {
  if (state === null) return { current: "check", failure: null, stoppedAt: null, finished: false };
  if (isFailure(state)) return { current: null, failure: state, stoppedAt: FAILED_AT[state], finished: false };
  const current = AT[state] ?? "check";
  return { current, failure: null, stoppedAt: null, finished: current === "done" };
}

/** Position in EARLY_STEPS, to tell whether a step is before the current one. */
export function stepIndex(step: EarlyStep): number {
  return EARLY_STEPS.indexOf(step);
}
