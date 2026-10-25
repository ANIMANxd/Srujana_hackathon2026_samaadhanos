// API client for contract v1.0. Same-origin /api/v1/* is proxied to FastAPI by
// next.config.ts. When the backend is unreachable, preset cases fall back to
// the synced fixtures and the caller is told the data is offline (F1).
// No legal math here: requests and responses pass through untouched.

import { artifactFixture, asExtraction, asRequest, asResponse, fixtureFor, FIXTURES } from "./fixtures";
import type {
  ArtifactKind,
  ArtifactResponse,
  CaseRequest,
  CaseResponse,
  ExtractionResponse,
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
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorEnvelope = { error: { code: string; message: string; field?: string | null } };

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
  if (isEnvelope(body)) throw new ApiError(res.status, body.error.code, body.error.message, body.error.field ?? null);
  // A 5xx without the contract envelope is the dev proxy failing to reach FastAPI.
  if (res.status >= 500) throw new BackendUnreachable(`Backend answered ${res.status}`);
  throw new ApiError(res.status, `HTTP_${res.status}`, res.statusText || "Request failed");
}

function postJson<T>(path: string, payload: unknown): Promise<T> {
  return call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

// ------------------------------------------------------------ endpoints ----

export async function health(): Promise<boolean> {
  try {
    await call<unknown>("/health");
    return true;
  } catch {
    return false;
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
