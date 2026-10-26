// What the owner changed from the duplicates review, kept in this browser so the
// change can be undone from the toast now and from a profile page later. The
// server audits every change itself; this log is only a per-viewer convenience
// (CR-19 asks for a server list), so every read and write is guarded.

import { announceBookChange } from "./customerBook";
import { BackendUnreachable, detachCustomer, undoDismissSuggestion, unlinkFromGroup, type MutationOptions } from "./api";
import { idempotencyKeyFor, releaseIdempotencyKey } from "./idempotency";

export type ReviewChange =
  | { id: string; kind: "ATTACH"; at: string; sourceId: string; targetId: string; sourceName: string; targetName: string }
  | { id: string; kind: "GROUP"; at: string; groupId: string; label: string; memberIds: string[] }
  | { id: string; kind: "DISMISS"; at: string; a: string; b: string };

const STORE = "samaadhan-review-log";
const KEEP = 30;

function read(): ReviewChange[] {
  try {
    const raw = window.localStorage.getItem(STORE);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as ReviewChange[]) : [];
  } catch {
    return [];
  }
}

function write(list: ReviewChange[]): void {
  try {
    window.localStorage.setItem(STORE, JSON.stringify(list.slice(0, KEEP)));
  } catch {
    /* storage blocked: the toast Undo still works for this session */
  }
}

/** Changes not yet undone that involve this customer, newest first. */
export function changesFor(customerId: string): ReviewChange[] {
  return read().filter((c) => involves(c, customerId));
}

export function involves(c: ReviewChange, customerId: string): boolean {
  if (c.kind === "ATTACH") return c.sourceId === customerId || c.targetId === customerId;
  if (c.kind === "GROUP") return c.memberIds.includes(customerId);
  return c.a === customerId || c.b === customerId;
}

export function recordChange(c: ReviewChange): void {
  write([c, ...read().filter((x) => x.id !== c.id)]);
}

export function forgetChange(id: string): void {
  write(read().filter((c) => c.id !== id));
}

export function newChangeId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** The server calls that reverse one change. Each has its own Idempotency-Key, released when it lands. */
export async function undoChange(c: ReviewChange): Promise<void> {
  const run = async (actionId: string, fn: (opts: MutationOptions) => Promise<void>) => {
    try {
      await fn({ idempotencyKey: idempotencyKeyFor(actionId) });
    } catch (e) {
      // A dropped connection keeps the key so a retry replays; a definite answer releases it.
      if (!(e instanceof BackendUnreachable)) releaseIdempotencyKey(actionId);
      throw e;
    }
    releaseIdempotencyKey(actionId);
  };
  if (c.kind === "ATTACH") {
    await run(`review.undo:${c.id}`, (opts) => detachCustomer(c.targetId, c.sourceId, opts));
  } else if (c.kind === "GROUP") {
    for (const m of c.memberIds) await run(`review.undo:${c.id}:${m}`, (opts) => unlinkFromGroup(c.groupId, m, opts));
  } else {
    await run(`review.undo:${c.id}`, (opts) => undoDismissSuggestion(c.a, c.b, opts));
  }
  forgetChange(c.id);
  announceBookChange();
}
