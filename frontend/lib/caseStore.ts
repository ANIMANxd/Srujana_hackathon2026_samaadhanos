// Per-browser storage for edited and uploaded case INPUTS (never outputs).
// Every access is wrapped: storage may be blocked (private window), and the app
// must still work without it.

import { useMemo, useSyncExternalStore } from "react";
import { asRequest } from "./fixtures";
import type { CaseRequest, Stage } from "./types";

const PREFIX = "samaadhan:";

function read(store: "session" | "local", key: string): string | null {
  try {
    return (store === "session" ? window.sessionStorage : window.localStorage).getItem(PREFIX + key);
  } catch {
    return null;
  }
}

function write(store: "session" | "local", key: string, value: string | null): void {
  try {
    const s = store === "session" ? window.sessionStorage : window.localStorage;
    if (value === null) s.removeItem(PREFIX + key);
    else s.setItem(PREFIX + key, value);
  } catch {
    /* storage unavailable: edits live only in memory */
  }
}

function readRequest(store: "session" | "local", key: string): CaseRequest | null {
  const raw = read(store, key);
  if (!raw) return null;
  try {
    return asRequest(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function getEdited(id: string): CaseRequest | null {
  return readRequest("session", `edited:${id}`);
}

export function setEdited(id: string, request: CaseRequest | null): void {
  write("session", `edited:${id}`, request ? JSON.stringify(request) : null);
}

/** Uploaded-and-approved cases are kept on this device (local storage). */
export function saveUploaded(request: CaseRequest): void {
  write("local", `uploaded:${request.case_id}`, JSON.stringify(request));
  const ids = listUploadedIds();
  if (!ids.includes(request.case_id)) write("local", "uploaded-ids", JSON.stringify([...ids, request.case_id]));
}

export function getUploaded(id: string): CaseRequest | null {
  return readRequest("local", `uploaded:${id}`);
}

export function listUploadedIds(): string[] {
  const raw = read("local", "uploaded-ids");
  if (!raw) return [];
  try {
    const v: unknown = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export type SendLogEntry = { stage: Stage; at: string };

const noopSubscribe = () => () => {};

/** Reads the log without a hydration mismatch (server snapshot is empty). */
export function useSendLog(id: string): SendLogEntry[] {
  const raw = useSyncExternalStore(
    noopSubscribe,
    () => read("local", `sendlog:${id}`) ?? "",
    () => "",
  );
  return useMemo(() => parseLog(raw), [raw]);
}

function parseLog(raw: string): SendLogEntry[] {
  if (!raw) return [];
  try {
    const v: unknown = JSON.parse(raw);
    return Array.isArray(v) ? (v as SendLogEntry[]).filter((e) => typeof e?.at === "string") : [];
  } catch {
    return [];
  }
}

export function getSendLog(id: string): SendLogEntry[] {
  return parseLog(read("local", `sendlog:${id}`) ?? "");
}

/** `at` is the device's local date (YYYY-MM-DD): a log entry, not a legal date. */
export function logPrepared(id: string, stage: Stage, at: string): void {
  const log = getSendLog(id);
  write("local", `sendlog:${id}`, JSON.stringify([...log, { stage, at }]));
}

export function sameRequest(a: CaseRequest | null, b: CaseRequest | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
