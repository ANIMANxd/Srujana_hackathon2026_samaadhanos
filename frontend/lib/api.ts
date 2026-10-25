// API client for contract v1.0 and v1.1. Same-origin /api/v1/* is proxied to FastAPI by
// next.config.ts. When the backend is unreachable, preset cases fall back to
// the synced fixtures and the caller is told the data is offline (F1).
// No legal math here: requests and responses pass through untouched.

import { artifactFixture, asExtraction, asRequest, asResponse, fixtureFor, FIXTURES } from "./fixtures";
import {
  offlineBids,
  offlineCaseDetail,
  offlineCases,
  offlineChainResult,
  offlineDeliveries,
  offlineEsign,
  offlineEvents,
  offlineOptions,
  offlinePayout,
} from "./fixturesV4";
import type {
  ArtifactKind,
  ArtifactResponse,
  AuditEvent,
  Bid,
  CaseDetail,
  CaseRequest,
  CaseSummary,
  CaseResponse,
  ChainVerifyResult,
  ESignSession,
  ExtractionResponse,
  OptionsResponse,
  PayoutStatus,
  WebhookDelivery,
  PresetSummary,
  SettlementSimulationResponse,
  StatuteConfig,
} from "./types";

const BASE = "/api/v1";
const TIMEOUT_MS = 8000;

export type Source = "live" | "offline";
export type Sourced<T> = { data: T; source: Source };

/** The backend could not be reached at all (network, proxy, or timeout). */
export class BackendUnreachable extends Error {
  constructor(message = "Backend unreachable") {
    super(message);
    this.name = "BackendUnreachable";
  }
}

/** The backend answered with the contract error envelope {error:{code,message,field?}}. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public field: string | null = null,
    /** The v1.1 envelope's `details`, when the server sent one. */
    public details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorEnvelope = { error: { code: string; message: string; field?: string | null; details?: Record<string, unknown> | null } };

function isEnvelope(v: unknown): v is ErrorEnvelope {
  if (typeof v !== "object" || v === null || !("error" in v)) return false;
  const e = (v as { error: unknown }).error;
  return typeof e === "object" && e !== null && "code" in e && "message" in e;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, signal: controller.signal, cache: "no-store" });
  } catch {
    throw new BackendUnreachable();
  } finally {
    clearTimeout(timer);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (res.ok) return body as T;
  if (isEnvelope(body)) throw new ApiError(res.status, body.error.code, body.error.message, body.error.field ?? null, body.error.details ?? null);
  // A 5xx without the contract envelope is the dev proxy failing to reach FastAPI.
  if (res.status >= 500) throw new BackendUnreachable(`Backend answered ${res.status}`);
  throw new ApiError(res.status, `HTTP_${res.status}`, res.statusText || "Request failed");
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

/**
 * Headers every v1.1 mutation carries (architecture_v4 §8): `idempotencyKey`
 * is required; `ifMatch` is the track version the screen last saw. A stale
 * version answers 409 and the caller refreshes.
 */
export type MutationOptions = { idempotencyKey: string; ifMatch?: number };

function mutate<T>(path: string, opts: MutationOptions, payload?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Idempotency-Key": opts.idempotencyKey };
  if (payload !== undefined) headers["Content-Type"] = "application/json";
  if (opts.ifMatch !== undefined) headers["If-Match"] = String(opts.ifMatch);
  return call<T>(path, { method: "POST", headers, body: payload === undefined ? undefined : JSON.stringify(payload) });
}

const caseUrl = (id: string) => `/cases/${encodeURIComponent(id)}`;

// ------------------------------------------------------------ endpoints ----

export async function health(): Promise<boolean> {
  try {
    await call<unknown>("/health");
    return true;
  } catch {
    return false;
  }
}

/** GET /health as the backend sent it (string values), or null when unreachable. */
export async function getHealth(): Promise<Record<string, string> | null> {
  try {
    return await call<Record<string, string>>("/health");
  } catch {
    return null;
  }
}

export async function listPresets(): Promise<Sourced<PresetSummary[]>> {
  try {
    const body = await call<{ presets: PresetSummary[] }>("/presets");
    return { data: body.presets, source: "live" };
  } catch (e) {
    if (!(e instanceof BackendUnreachable)) throw e;
    return { data: FIXTURES.map((f) => ({ id: f.id, title: f.title })), source: "offline" };
  }
}

/** A preset's input-only request (CQ-3 shape: {id, title, request}). */
export async function getPresetRequest(id: string): Promise<Sourced<{ title: string; request: CaseRequest }>> {
  try {
    const body = await call<{ id: string; title: string; request: unknown }>(`/presets/${encodeURIComponent(id)}`);
    const request = asRequest(body.request);
    if (!request) throw new ApiError(500, "BAD_PRESET", "The preset file is malformed.");
    return { data: { title: body.title, request }, source: "live" };
  } catch (e) {
    if (!(e instanceof BackendUnreachable)) throw e;
    const f = fixtureFor(id);
    if (!f) throw e;
    return { data: { title: f.title, request: f.request }, source: "offline" };
  }
}

export async function evaluate(request: CaseRequest): Promise<CaseResponse> {
  const body = await postJson<unknown>("/evaluate-case", request);
  const response = asResponse(body);
  if (!response) throw new ApiError(500, "BAD_RESPONSE", "The engine response did not match the contract.");
  return response;
}

/** Offline fallback for an UNEDITED preset only. Edited requests never get fixture numbers. */
export function offlineResponseFor(id: string): CaseResponse | null {
  return fixtureFor(id)?.response ?? null;
}

export async function getConfig(): Promise<StatuteConfig | null> {
  try {
    return await call<StatuteConfig>("/config");
  } catch {
    return null;
  }
}

/**
 * POST /extract-evidence (B9): a plain-text upload (invoice or PO text, or a
 * WhatsApp .txt export) in, machine-suggested candidates out. Nothing here is
 * evaluated; a person confirms the values first.
 */
export async function extractEvidence(file: Blob, filename: string): Promise<ExtractionResponse> {
  const form = new FormData();
  form.append("file", file, filename);
  const body = await call<unknown>("/extract-evidence", { method: "POST", body: form });
  const response = asExtraction(body);
  if (!response) throw new ApiError(500, "BAD_RESPONSE", "The extraction result did not match the contract.");
  return response;
}

/**
 * POST /simulate-settlement (8.1). The backend evaluates the case first, so the
 * split always uses the engine's own claim; the browser only sends the terms.
 */
export async function simulateSettlement(
  request: CaseRequest,
  terms: { upfront_pct: string; waiver_pct: string; days_to_second_payment: number },
): Promise<SettlementSimulationResponse> {
  return postJson<SettlementSimulationResponse>("/simulate-settlement", { request, ...terms });
}

// ------------------------------------------------------------ artifacts ----

/** A drafted artifact and where it came from (live engine or saved sample). */
export type SourcedArtifact = Sourced<ArtifactResponse>;

/**
 * POST /generate-artifact (B8). The backend evaluates the case itself, so the
 * draft only ever carries engine figures. Offline, an UNEDITED preset falls
 * back to the engine-generated sample saved in contracts/fixtures; anything
 * else returns null so the caller can say the draft needs the backend.
 */
export async function generateArtifact(
  kind: ArtifactKind,
  request: CaseRequest,
  offlineCaseId: string | null,
): Promise<SourcedArtifact | null> {
  try {
    const body = await postJson<ArtifactResponse>("/generate-artifact", { kind, request });
    if (typeof body?.markdown !== "string") throw new ApiError(500, "BAD_RESPONSE", "The draft did not match the contract.");
    return { data: body, source: "live" };
  } catch (e) {
    if (!(e instanceof BackendUnreachable)) throw e;
    const markdown = offlineCaseId ? artifactFixture(offlineCaseId, kind) : null;
    if (markdown === null) return null;
    return {
      data: { contract_version: "1.0", kind, filename: `${offlineCaseId}.${kind}.md`, markdown, warnings: [] },
      source: "offline",
    };
  }
}

// ------------------------------------------------- contract v1.1: cases ----
//
// Shapes that architecture_v4 §9 does not spell out are assumed, not invented
// silently: POST /cases takes the approved CaseEvaluationRequest and answers
// with a CaseDetail; the track actions answer with the refreshed CaseDetail
// (select-bid answers with the ESignSession it creates). Raised in the worklog.

/** Offline reads fall back to the saved v1.1 samples; a sample is never your own case. */
async function readOrSample<T>(live: () => Promise<T>, sample: () => T | null): Promise<Sourced<T>> {
  try {
    return { data: await live(), source: "live" };
  } catch (e) {
    if (!(e instanceof BackendUnreachable)) throw e;
    const data = sample();
    if (data === null) throw e;
    return { data, source: "offline" };
  }
}

/** POST /cases: store the approved case; the server issues the id. */
export function createCase(request: CaseRequest, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>("/cases", opts, request);
}

/** GET /cases: one summary per stored case (the Dues home). Offline: the saved sample case. */
export function listCases(): Promise<Sourced<CaseSummary[]>> {
  return readOrSample(
    async () => {
      const body = await call<{ cases: CaseSummary[] }>("/cases");
      if (!Array.isArray(body?.cases)) throw new ApiError(500, "BAD_RESPONSE", "The case list did not match the contract.");
      return body.cases;
    },
    offlineCases,
  );
}

/** GET /cases/{id}. `offlineState` picks which saved sample stands in when the backend is down. */
export function getCase(id: string, offlineState?: string | null): Promise<Sourced<CaseDetail>> {
  return readOrSample(
    async () => {
      const body = await call<CaseDetail>(caseUrl(id));
      if (typeof body?.case?.id !== "string") throw new ApiError(500, "BAD_RESPONSE", "The case did not match the contract.");
      return body;
    },
    () => offlineCaseDetail(offlineState),
  );
}

/** GET /cases/{id}/options: the two-option comparison. `recommendation` is always null. */
export function getOptions(
  id: string,
  expectedPaymentDate?: string,
  offlineVariant?: string | null,
): Promise<Sourced<OptionsResponse>> {
  const q = expectedPaymentDate ? `?expected_payment_date=${encodeURIComponent(expectedPaymentDate)}` : "";
  return readOrSample(() => call<OptionsResponse>(`${caseUrl(id)}/options${q}`), () => offlineOptions(offlineVariant));
}

// ------------------------------------------------ contract v1.1: financing --

export function startFinancing(id: string, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(id)}/financing`, opts);
}

export function requestBuyerAcceptance(id: string, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(id)}/financing/buyer-acceptance`, opts);
}

export function listBids(id: string): Promise<Sourced<Bid[]>> {
  return readOrSample(() => call<Bid[]>(`${caseUrl(id)}/financing/bids`), offlineBids);
}

/** Selecting a bid creates the (mock) eSign session. */
export function selectBid(id: string, bidId: string, opts: MutationOptions): Promise<ESignSession> {
  return mutate<ESignSession>(`${caseUrl(id)}/financing/bids/${encodeURIComponent(bidId)}/select`, opts);
}

// ASSUMED routes (not in architecture_v4 section 9; raised in the worklog): the
// signing session and the payout have no read endpoint there, and the OTP step
// has no submit endpoint. Case-scoped like the rest of the financing routes.

/** The (mock) eSign session of the selected bid. */
export function getEsignSession(id: string): Promise<Sourced<ESignSession>> {
  return readOrSample(() => call<ESignSession>(`${caseUrl(id)}/financing/esign`), offlineEsign);
}

/** The TEMPLATE PDF the signature is for (assumed route; opened in a new tab, never fetched here). */
export function esignTemplateUrl(id: string): string {
  return `${BASE}${caseUrl(id)}/financing/esign/template.pdf`;
}

/** Submit the demo OTP. No Aadhaar field exists anywhere in this call. */
export function submitEsignOtp(id: string, otp: string, opts: MutationOptions): Promise<ESignSession> {
  return mutate<ESignSession>(`${caseUrl(id)}/financing/esign/otp`, opts, { otp });
}

/** The (mock) payout: its MOCK reference, UTR and amount. */
export function getPayout(id: string): Promise<Sourced<PayoutStatus>> {
  return readOrSample(() => call<PayoutStatus>(`${caseUrl(id)}/financing/payout`), offlinePayout);
}

export function cancelFinancing(id: string, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(id)}/financing/cancel`, opts);
}

// ------------------------------------------------- contract v1.1: recovery --

/** Start or resume recovery; `stage` prepares that stage's draft (nothing is sent). */
export function startRecovery(id: string, stage: number | null, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(id)}/recovery`, opts, { stage });
}

/** The owner confirms they sent the draft themselves. */
export function markRecoverySent(id: string, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(id)}/recovery/mark-sent`, opts);
}

// ------------------------------------------- contract v1.1: audit + stream --

export function getEvents(id: string): Promise<Sourced<AuditEvent[]>> {
  return readOrSample(() => call<AuditEvent[]>(`${caseUrl(id)}/events`), offlineEvents);
}

export function verifyEvents(id: string): Promise<Sourced<ChainVerifyResult>> {
  return readOrSample(() => call<ChainVerifyResult>(`${caseUrl(id)}/events/verify`), offlineChainResult);
}

/** Same-origin URL for `EventSource` (GET /cases/{id}/stream, server-sent events). */
export function streamUrl(id: string): string {
  return `${BASE}${caseUrl(id)}/stream`;
}

// ---------------------------------------------- contract v1.1: judge mocks --
// Judge console only; the server disables these in production. Bodies are the
// mock provider's own scenario/clock settings, so they pass through as plain JSON.

export type MockBody = Record<string, string | number | boolean | null>;

export function setMockScenario(body: MockBody, opts: MutationOptions): Promise<MockBody> {
  return mutate<MockBody>("/mock/scenarios", opts, body);
}

export function setMockClock(body: MockBody, opts: MutationOptions): Promise<MockBody> {
  return mutate<MockBody>("/mock/clock", opts, body);
}

/**
 * GET /mock/deliveries (ASSUMED route, judge console only): the webhook inbox as
 * the API saw it, newest first. Offline it shows the saved sample log.
 */
export function getDeliveries(): Promise<Sourced<WebhookDelivery[]>> {
  return readOrSample(() => call<WebhookDelivery[]>("/mock/deliveries"), offlineDeliveries);
}

// POST /webhooks/{esign,marketplace,disbursement} are signed provider-to-server
// callbacks: the browser never calls them, so there is deliberately no client.
