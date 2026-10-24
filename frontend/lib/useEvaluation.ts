"use client";

// One hook per case screen (architecture §10, F1): resolves the case's input,
// evaluates it through the engine (debounced), keeps the last good result,
// and falls back to bundled fixtures offline for unedited presets only.

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, BackendUnreachable, evaluate, getPresetRequest, offlineResponseFor, type Source } from "./api";
import { getEdited, getUploaded, sameRequest, setEdited } from "./caseStore";
import { demoFor } from "./fixtures";
import type { CaseRequest, CaseResponse } from "./types";

export type CaseOrigin = "preset" | "demo" | "upload";

export type EvaluationStatus = "loading" | "ready" | "needs_backend" | "error" | "not_found";

export type Evaluation = {
  caseId: string;
  title: string | null;
  origin: CaseOrigin | null;
  base: CaseRequest | null;
  request: CaseRequest | null;
  response: CaseResponse | null;
  status: EvaluationStatus;
  source: Source | null;
  error: string | null;
  refreshing: boolean;
  isEdited: boolean;
  setRequest: (next: CaseRequest) => void;
  reset: () => void;
  retry: () => void;
};

const DEBOUNCE_MS = 300;

type Resolved = { title: string | null; origin: CaseOrigin; base: CaseRequest };

async function resolveBase(caseId: string): Promise<Resolved | null> {
  const uploaded = getUploaded(caseId);
  if (uploaded) return { title: null, origin: "upload", base: uploaded };
  const demo = demoFor(caseId);
  if (demo) return { title: demo.title, origin: "demo", base: demo.request };
  try {
    const p = await getPresetRequest(caseId);
    return { title: p.data.title, origin: "preset", base: p.data.request };
  } catch {
    return null;
  }
}

export function useEvaluation(caseId: string): Evaluation {
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const [request, setRequestState] = useState<CaseRequest | null>(null);
  const [response, setResponse] = useState<CaseResponse | null>(null);
  const [status, setStatus] = useState<EvaluationStatus>("loading");
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);

  // 1. Resolve the case input.
  useEffect(() => {
    let cancelled = false;
    resolveBase(caseId).then((r) => {
      if (cancelled) return;
      if (!r) {
        setStatus("not_found");
        return;
      }
      setResolved(r);
      setRequestState(getEdited(caseId) ?? r.base);
    });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // 2. Evaluate whenever the request changes (debounced for live edits).
  useEffect(() => {
    if (!request || !resolved) return;
    const mine = ++seq.current;
    const unedited = sameRequest(request, resolved.base);
    const timer = setTimeout(async () => {
      setRefreshing(true);
      try {
        const res = await evaluate(request);
        if (mine !== seq.current) return;
        setResponse(res);
        setSource("live");
        setStatus("ready");
        setError(null);
      } catch (e) {
        if (mine !== seq.current) return;
        if (e instanceof BackendUnreachable) {
          const fixture = unedited && resolved.origin === "preset" ? offlineResponseFor(caseId) : null;
          if (fixture) {
            setResponse(fixture);
            setSource("offline");
            setStatus("ready");
          } else {
            // Never show numbers that belong to a different input.
            setResponse(null);
            setSource("offline");
            setStatus("needs_backend");
          }
          setError(null);
        } else {
          // Keep the last good result on screen and explain what failed.
          setError(e instanceof ApiError ? e.message : "The engine could not evaluate this case.");
          setStatus((s) => (s === "ready" ? "ready" : "error"));
        }
      } finally {
        if (mine === seq.current) setRefreshing(false);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [request, resolved, caseId, attempt]);

  const setRequest = useCallback(
    (next: CaseRequest) => {
      setRequestState(next);
      setEdited(caseId, resolved && sameRequest(next, resolved.base) ? null : next);
    },
    [caseId, resolved],
  );

  const reset = useCallback(() => {
    if (!resolved) return;
    setEdited(caseId, null);
    setRequestState(resolved.base);
  }, [caseId, resolved]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return {
    caseId,
    title: resolved?.title ?? null,
    origin: resolved?.origin ?? null,
    base: resolved?.base ?? null,
    request,
    response,
    status,
    source,
    error,
    refreshing,
    isEdited: Boolean(request && resolved && !sameRequest(request, resolved.base)),
    setRequest,
    reset,
    retry,
  };
}
