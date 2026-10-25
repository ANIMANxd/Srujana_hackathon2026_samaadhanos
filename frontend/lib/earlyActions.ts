"use client";

// The Get-paid-early actions and reads, from the real API or, when the backend's
// mock providers are down, from the labelled demo simulation (lib/sim.ts). One
// place decides, so no screen needs to know which it is talking to.

import {
  cancelFinancing,
  getEsignSession,
  getPayout,
  listBids,
  requestBuyerAcceptance,
  selectBid,
  startFinancing,
  submitEsignOtp,
  type MutationOptions,
  type Sourced,
} from "./api";
import { simBids, simCancel, simEsign, simPayout, simRequestAcceptance, simSelect, simSign, simStart, useSimulation } from "./sim";
import type { Bid, ESignSession, PayoutStatus } from "./types";

export type EarlyActions = {
  simulated: boolean;
  start: (caseId: string, opts: MutationOptions) => Promise<void>;
  requestAcceptance: (caseId: string, opts: MutationOptions) => Promise<void>;
  select: (caseId: string, bidId: string, opts: MutationOptions) => Promise<void>;
  submitOtp: (caseId: string, otp: string, opts: MutationOptions) => Promise<void>;
  cancel: (caseId: string, opts: MutationOptions) => Promise<void>;
  bids: (caseId: string) => Promise<Sourced<Bid[]>>;
  esign: (caseId: string) => Promise<Sourced<ESignSession>>;
  payout: (caseId: string) => Promise<Sourced<PayoutStatus>>;
};

const live = <T>(data: T): Sourced<T> => ({ data, source: "live" });

export function useEarlyActions(): EarlyActions {
  const simulated = useSimulation();
  if (simulated) {
    return {
      simulated,
      start: async (id) => simStart(id),
      requestAcceptance: async (id) => simRequestAcceptance(id),
      select: async (id, bidId) => simSelect(id, bidId),
      submitOtp: async (id) => simSign(id),
      cancel: async (id) => simCancel(id),
      bids: async (id) => live(simBids(id)),
      esign: async (id) => {
        const s = simEsign(id);
        if (!s) throw new Error("No signing session");
        return live(s);
      },
      payout: async (id) => {
        const p = simPayout(id);
        if (!p) throw new Error("No payout yet");
        return live(p);
      },
    };
  }
  return {
    simulated,
    start: async (id, opts) => void (await startFinancing(id, opts)),
    requestAcceptance: async (id, opts) => void (await requestBuyerAcceptance(id, opts)),
    select: async (id, bidId, opts) => void (await selectBid(id, bidId, opts)),
    submitOtp: async (id, otp, opts) => void (await submitEsignOtp(id, otp, opts)),
    cancel: async (id, opts) => void (await cancelFinancing(id, opts)),
    bids: listBids,
    esign: getEsignSession,
    payout: getPayout,
  };
}
