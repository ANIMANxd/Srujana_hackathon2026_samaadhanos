"use client";

// Demo simulation of Get paid early (Option 1), used only when the backend says
// its mock providers are unreachable (`/health` -> `mock_providers: unreachable`),
// because then the real flow can never get past "waiting for the buyer".
//
// Everything here is a labelled DEMO: the bids, e-sign session and payout are the
// saved samples from contracts/fixtures/v4 (their money was produced by the
// backend's finance module, never worked out in the browser). The record lives in
// this browser only, and `useTrack` shows it in place of the server's track.

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { getHealth } from "./api";
import { offlineBids, offlineCaseDetail, offlineEsign, offlinePayout } from "./fixturesV4";
import type { Bid, CaseDetail, CaseSummary, ESignSession, PayoutStatus, TrackState } from "./types";

type Step = { at: number; state: TrackState };

export type SimRecord = {
  state: TrackState;
  version: number;
  /** What the judge console asked the mock providers to do next (buyer_rejects, no_bids, ...). */
  scenario: string;
  bids: Bid[] | null;
  bidId: string | null;
  signedAt: string | null;
  schedule: Step[];
};

const PREFIX = "samaadhan:sim:";
const listeners = new Set<() => void>();

const key = (caseId: string) => PREFIX + caseId;

function readRaw(caseId: string): string {
  try {
    return window.localStorage.getItem(key(caseId)) ?? "";
  } catch {
    return "";
  }
}

function parse(raw: string): SimRecord | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SimRecord;
  } catch {
    return null;
  }
}

function write(caseId: string, rec: SimRecord | null): void {
  try {
    if (rec) window.localStorage.setItem(key(caseId), JSON.stringify(rec));
    else window.localStorage.removeItem(key(caseId));
  } catch {
    /* storage blocked: the simulation simply does not persist */
  }
  listeners.forEach((l) => l());
}

/** Apply any step whose time has come. Returns the record to store, or the same one. */
function settle(rec: SimRecord): SimRecord {
  const now = Date.now();
  const due = rec.schedule.filter((s) => s.at <= now);
  if (due.length === 0) return rec;
  const last = due[due.length - 1];
  return { ...rec, state: last.state, version: rec.version + due.length, schedule: rec.schedule.filter((s) => s.at > now) };
}

function get(caseId: string): SimRecord | null {
  const rec = parse(readRaw(caseId));
  if (!rec) return null;
  const settled = settle(rec);
  if (settled !== rec) write(caseId, settled);
  return settled;
}

function set(caseId: string, patch: Partial<SimRecord>, schedule: { after: number; state: TrackState }[] = []): void {
  const cur = get(caseId);
  const base: SimRecord = cur ?? { state: "FINANCEABLE", version: 0, scenario: "happy_path", bids: null, bidId: null, signedAt: null, schedule: [] };
  const now = Date.now();
  write(caseId, {
    ...base,
    ...patch,
    version: base.version + 1,
    schedule: schedule.map((s) => ({ at: now + s.after, state: s.state })),
  });
}

/** Bids are the saved samples, with fresh valid-until times; every amount is the sample's own. */
function sampleBids(): Bid[] {
  const now = Date.now();
  return (offlineBids() ?? []).map((b, i) => ({ ...b, status: "AVAILABLE", valid_until: new Date(now + (20 + i) * 3_600_000).toISOString() }));
}

// ------------------------------------------------------------- actions ----

export function simStart(caseId: string): void {
  set(caseId, { state: "FINANCEABLE", bids: null, bidId: null, signedAt: null });
}

export function simRequestAcceptance(caseId: string): void {
  const sc = get(caseId)?.scenario ?? "happy_path";
  if (sc === "buyer_rejects") set(caseId, { state: "AWAITING_BUYER_ACCEPTANCE" }, [{ after: 2500, state: "BUYER_DECLINED" }]);
  else if (sc === "no_bids")
    set(caseId, { state: "AWAITING_BUYER_ACCEPTANCE" }, [
      { after: 2000, state: "BIDDING_OPEN" },
      { after: 4500, state: "NO_BIDS" },
    ]);
  else set(caseId, { state: "AWAITING_BUYER_ACCEPTANCE", bids: sampleBids() }, [{ after: 2500, state: "BIDS_AVAILABLE" }]);
}

export function simSelect(caseId: string, bidId: string): void {
  set(caseId, { state: "AWAITING_ESIGN", bidId });
}

export function simSign(caseId: string): void {
  set(caseId, { signedAt: new Date().toISOString() }, [
    { after: 1500, state: "AWAITING_DISBURSEMENT" },
    { after: 4500, state: "DISBURSED" },
  ]);
}

export function simCancel(caseId: string): void {
  set(caseId, { state: "CANCELLED" });
}

export function simSetScenario(caseId: string, scenario: string): void {
  set(caseId, { scenario });
}

/** Back to the server's own track (used when the owner switches to recovery). */
export function simClear(caseId: string): void {
  if (readRaw(caseId)) write(caseId, null);
}

// --------------------------------------------------------------- reads ----

export function simBids(caseId: string): Bid[] {
  const rec = get(caseId);
  return (rec?.bids ?? []).map((b) => (b.id === rec?.bidId ? { ...b, status: "SELECTED" as const } : b));
}

export function simEsign(caseId: string): ESignSession | null {
  const rec = get(caseId);
  const sample = offlineEsign();
  if (!rec || !sample) return null;
  const signed = rec.signedAt !== null;
  return {
    ...sample,
    status: signed ? "SIGNED" : "PENDING",
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    signed_at: rec.signedAt,
    signed_doc_sha256: signed ? sample.signed_doc_sha256 : null,
    signer_display: signed ? sample.signer_display : null,
  };
}

export function simPayout(caseId: string): PayoutStatus | null {
  const rec = get(caseId);
  const sample = offlinePayout();
  if (!rec || !sample) return null;
  const chosen = rec.bids?.find((b) => b.id === rec.bidId);
  const done = rec.state === "DISBURSED";
  return { ...sample, amount: chosen?.net_amount ?? sample.amount, status: done ? "PROCESSED" : "PENDING", settled_at: done ? new Date().toISOString() : null, utr: done ? sample.utr : null };
}

/** The actions the server would offer in a state: the saved samples already list them per state. */
export function simActions(state: TrackState): string[] {
  if (state === "BIDDING_OPEN") return ["cancel_financing"];
  if (state === "CANCELLED") return ["switch_to_recovery"];
  return offlineCaseDetail(state)?.available_actions ?? [];
}

/** The track the simulation shows, shaped like the server's. */
export function simTrack(caseId: string, rec: SimRecord): NonNullable<CaseDetail["active_track"]> {
  return { id: "MOCK-TRK-SIM", case_id: caseId, kind: "FINANCING", state: rec.state, version: rec.version, created_at: new Date().toISOString(), closed_at: null };
}

// --------------------------------------------------------------- hooks ----

let healthPromise: Promise<boolean> | null = null;

/** True when the backend's mock providers are unreachable, so the real Option 1 flow cannot finish. */
export function useSimulation(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    let alive = true;
    healthPromise ??= getHealth().then((h) => h?.mock_providers === "unreachable");
    healthPromise.then((v) => alive && setOn(v));
    return () => {
      alive = false;
    };
  }, []);
  return on;
}

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => e.key?.startsWith(PREFIX) && cb();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
};

/** The simulation record for a case, re-read when it changes and when a scheduled step comes due. */
export function useSimRecord(caseId: string): SimRecord | null {
  const raw = useSyncExternalStore(
    subscribe,
    () => readRaw(caseId),
    () => "",
  );
  const rec = useMemo(() => parse(raw), [raw]);
  const waiting = (rec?.schedule.length ?? 0) > 0;
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => get(caseId), 500);
    return () => clearInterval(id);
  }, [waiting, caseId]);
  return rec;
}

/** Dues rows with the demo track shown where one exists, so a row matches its case page. */
export function useSimulatedCases(cases: CaseSummary[]): CaseSummary[] {
  const on = useSimulation();
  const raw = useSyncExternalStore(
    subscribe,
    () => cases.map((c) => readRaw(c.id)).join(""),
    () => "",
  );
  const pending = on && raw.includes('"schedule":[{');
  useEffect(() => {
    if (!pending) return;
    const id = setInterval(() => cases.forEach((c) => get(c.id)), 1000);
    return () => clearInterval(id);
  }, [pending, cases]);
  return useMemo(
    () =>
      !on
        ? cases
        : cases.map((c) => {
            const rec = parse(readRaw(c.id));
            return rec ? { ...c, state: rec.state, active_track: simTrack(c.id, rec) } : c;
          }),
    // `raw` changes whenever any record does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [on, cases, raw],
  );
}
