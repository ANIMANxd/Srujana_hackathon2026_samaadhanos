"use client";

// One hook per case screen (architecture §10, F1): resolves the case's input,
// evaluates it through the engine (debounced), keeps the last good result,
// and falls back to bundled fixtures offline for unedited presets only.
//
// Three kinds of case (contract v1.1 made the first one the normal one):
//   server  a stored case with a server-issued id: input and latest evaluation
//           come from GET /cases/{id}, kept live by useTrack; only a local edit
//           re-evaluates, statelessly.
//   preset  a bundled sample case (case_01...), always stateless.
//   upload  an approved upload kept on this device, stateless. Also what the
//           Approve step falls back to when the backend has no /cases route.
// `?legacy=1` forces the stateless path for any id.

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, BackendUnreachable, evaluate, getPresetRequest, offlineResponseFor, type Source } from "./api";
import { getEdited, getUploaded, sameRequest, setEdited } from "./caseStore";
import { asRequest, asResponse, fixtureFor } from "./fixtures";
import type { CaseRequest, CaseResponse } from "./types";
import { useTrack, type TrackView } from "./useTrack";

export type CaseOrigin = "preset" | "upload" | "server";

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
  /** The preset id whose saved samples may stand in offline, or null (edited or uploaded). */
  offlineId: string | null;
  /** Live case + track for server cases; null for preset and upload cases. */
  tracking: TrackView | null;
  setRequest: (next: CaseRequest) => void;
  reset: () => void;
  retry: () => void;
};

const DEBOUNCE_MS = 300;

type Resolved = { title: string | null; origin: CaseOrigin; base: CaseRequest };

async function resolveBase(caseId: string): Promise<Resolved | null> {
  const uploaded = getUploaded(caseId);
  if (uploaded) return { title: null, origin: "upload", base: uploaded };
  try {
    const p = await getPresetRequest(caseId);
    return { title: p.data.title, origin: "preset", base: p.data.request };
  } catch {
    return null;
  }
}

type Mode = "pending" | "local" | "server";

const noopSubscribe = () => () => {};

export function useEvaluation(caseId: string): Evaluation {
  const search = useSearchParams();
  const legacy = search.get("legacy") === "1";
  const offlineState = search.get("state");
  // Storage is only readable on the client; the server render is the loading skeleton either way.
  // useSyncExternalStore keeps hydration identical to the server render ("pending"), then switches.
  const mode = useSyncExternalStore<Mode>(
    noopSubscribe,
    () => (legacy || getUploaded(caseId) || fixtureFor(caseId) ? "local" : "server"),
    () => "pending",
  );
  const tracking = useTrack(caseId, mode === "server", offlineState);
  const serverEval = useMemo(() => asResponse(tracking.caseDetail?.latest_evaluation), [tracking.caseDetail]);
  const [resolved, setResolved] = useState<Resolved | null>(null);
  const [request, setRequestState] = useState<CaseRequest | null>(null);
  const [response, setResponse] = useState<CaseResponse | null>(null);
  const [status, setStatus] = useState<EvaluationStatus>("loading");
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const seq = useRef(0);
  const firstLoad = useRef(true);

  // 1b. A server case resolves from GET /cases/{id}. The stored input never changes,
  // so it is resolved once (adjusting state while rendering, not in an effect);
  // later reads only refresh the stored evaluation.
  const storedInput = mode === "server" ? tracking.caseDetail?.case.input_json : undefined;
  const storedBase = storedInput ? asRequest(storedInput) : null;
  const storedBad = Boolean(storedInput) && !storedBase;
  const [syncedFor, setSyncedFor] = useState<string | null>(null);
  if (storedBase && syncedFor !== caseId) {
    setSyncedFor(caseId);
    setResolved({ title: null, origin: "server", base: storedBase });
    setRequestState(getEdited(caseId) ?? storedBase);
  }

  // 1c. A local case resolves from this device or the preset files.
  useEffect(() => {
    if (mode !== "local") return;
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
  }, [caseId, mode]);

  // 2. Evaluate whenever the request changes (debounced for live edits).
  useEffect(() => {
    if (!request || !resolved) return;
    const mine = ++seq.current;
    const unedited = sameRequest(request, resolved.base);
    // The first evaluation of a case is not an edit: start at once so a slow
    // backend is not made slower by the typing debounce. Edits keep the debounce.
    const delay = firstLoad.current ? 0 : DEBOUNCE_MS;
    // An unedited server case already has its stored evaluation (shown below): do not recompute.
    if (resolved.origin === "server" && unedited && serverEval) {
      firstLoad.current = false;
      return;
    }
    const timer = setTimeout(async () => {
      firstLoad.current = false;
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
    }, delay);
    return () => clearTimeout(timer);
  }, [request, resolved, caseId, attempt, serverEval]);

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

  const refreshTrack = tracking.refresh;
  const retry = useCallback(() => {
    setAttempt((n) => n + 1);
    refreshTrack();
  }, [refreshTrack]);

  const isEdited = Boolean(request && resolved && !sameRequest(request, resolved.base));

  // Server cases: the stored evaluation is the answer until the person edits the input,
  // and the server's own lookup decides "not found" and "could not load".
  const showStored = resolved?.origin === "server" && !isEdited && serverEval !== null;
  let outStatus: EvaluationStatus = showStored ? "ready" : status;
  let outError = showStored ? null : error;
  if (mode === "server" && !resolved) {
    if (tracking.status === "not_found") outStatus = "not_found";
    else if (storedBad) {
      outStatus = "error";
      outError = "The stored case did not match the contract.";
    } else if (tracking.status === "error") {
      outStatus = "error";
      outError = tracking.error;
    }
  }

  return {
    caseId,
    title: resolved?.title ?? null,
    origin: resolved?.origin ?? null,
    base: resolved?.base ?? null,
    request,
    response: showStored ? serverEval : response,
    status: outStatus,
    source: showStored ? (tracking.source ?? "live") : source,
    error: outError,
    refreshing,
    isEdited,
    offlineId: resolved?.origin === "preset" && !isEdited ? caseId : null,
    tracking: mode === "server" ? tracking : null,
    setRequest,
    reset,
    retry,
  };
}
