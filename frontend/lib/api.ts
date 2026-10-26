// API client for contract v1.0, v1.1 and v1.2. Same-origin /api/v1/* is proxied to FastAPI by
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
import {
  offlineCustomerGroups,
  offlineCustomerProfile,
  offlineCustomerRows,
  offlinePayments,
  offlinePortfolioInsights,
  offlineSuggestions,
  sortSampleRows,
} from "./fixturesV5";
import type {
  CustomerGroupRow,
  CustomerProfile,
  CustomerRow,
  ImportPreview,
  ImportResult,
  Payment,
  PaymentCreateRequest,
  PaymentListResponse,
  PortfolioInsights,
  Suggestion,
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
  FinancingActionResponse,
  OptionsResponse,
  PayoutStatus,
  RecoveryActionResponse,
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

function mutate<T>(path: string, opts: MutationOptions, payload?: unknown, method: "POST" | "DELETE" = "POST"): Promise<T> {
  const headers: Record<string, string> = { "Idempotency-Key": opts.idempotencyKey };
  if (payload !== undefined) headers["Content-Type"] = "application/json";
  if (opts.ifMatch !== undefined) headers["If-Match"] = String(opts.ifMatch);
  return call<T>(path, { method, headers, body: payload === undefined ? undefined : JSON.stringify(payload) });
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

export function startFinancing(id: string, opts: MutationOptions): Promise<FinancingActionResponse> {
  return mutate<FinancingActionResponse>(`${caseUrl(id)}/financing`, opts);
}

export function requestBuyerAcceptance(id: string, opts: MutationOptions): Promise<FinancingActionResponse> {
  return mutate<FinancingActionResponse>(`${caseUrl(id)}/financing/buyer-acceptance`, opts);
}

export function listBids(id: string): Promise<Sourced<Bid[]>> {
  // The route answers with the whole action wrapper; the bids are one field of it.
  return readOrSample(async () => (await call<FinancingActionResponse>(`${caseUrl(id)}/financing/bids`)).bids ?? [], offlineBids);
}

/** Selecting a bid creates the (mock) eSign session. */
export function selectBid(id: string, bidId: string, opts: MutationOptions): Promise<FinancingActionResponse> {
  return mutate<FinancingActionResponse>(`${caseUrl(id)}/financing/bids/${encodeURIComponent(bidId)}/select`, opts);
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

export function cancelFinancing(id: string, opts: MutationOptions): Promise<FinancingActionResponse> {
  return mutate<FinancingActionResponse>(`${caseUrl(id)}/financing/cancel`, opts);
}

// ------------------------------------------------- contract v1.1: recovery --

/** Start or resume recovery; `stage` prepares that stage's draft (nothing is sent). */
export function startRecovery(id: string, stage: number, opts: MutationOptions): Promise<RecoveryActionResponse> {
  return mutate<RecoveryActionResponse>(`${caseUrl(id)}/recovery`, opts, { stage });
}

/** The owner confirms they sent the draft themselves. */
export function markRecoverySent(id: string, opts: MutationOptions): Promise<RecoveryActionResponse> {
  return mutate<RecoveryActionResponse>(`${caseUrl(id)}/recovery/mark-sent`, opts);
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

// ------------------------------------------ contract v1.2: customer book ----
//
// v1.2 publishes the shapes (backend/app/schemas_v5.py) before the routes, so
// every path below is ASSUMED and listed in CONTRACT-REQUESTS.md (CR-15) for
// the API agent to confirm or correct. Lists accept either a bare array or the
// `{<name>: [...]}` wrapper GET /cases uses. Mutations whose answer has no
// contract shape return nothing: the screen re-reads instead of guessing.
// Every figure here is the server's; the browser sorts nothing by money.

/** A list body: a bare array, or `{[key]: array}`. Anything else is a contract mismatch. */
function listOf<T>(body: unknown, key: string): T[] {
  if (Array.isArray(body)) return body as T[];
  if (typeof body === "object" && body !== null && Array.isArray((body as Record<string, unknown>)[key])) {
    return (body as Record<string, unknown>)[key] as T[];
  }
  throw new ApiError(500, "BAD_RESPONSE", "The list did not match the contract.");
}

async function mutateVoid(path: string, opts: MutationOptions, payload?: unknown, method: "POST" | "DELETE" = "POST"): Promise<void> {
  await mutate<unknown>(path, opts, payload, method);
}

/**
 * The framework's own 404 for a path it has no route for ("Not Found"), as
 * opposed to a route saying a record does not exist (which names the record).
 */
function routeMissing(e: unknown): boolean {
  return e instanceof ApiError && e.status === 404 && (e.code === "NOT_FOUND" || e.code === "HTTP_404") && e.message === "Not Found";
}

/**
 * Like `readOrSample`, and a missing route also falls back: until the v1.2
 * routes ship (CR-15) a running backend answers 404 for every one of them.
 */
async function v12OrSample<T>(live: () => Promise<T>, sample: () => T | null): Promise<Sourced<T>> {
  try {
    return await readOrSample(live, sample);
  } catch (e) {
    if (!routeMissing(e)) throw e;
    const data = sample();
    if (data === null) throw e;
    return { data, source: "offline" };
  }
}

const customerUrl = (id: string) => `/customers/${encodeURIComponent(id)}`;
const groupUrl = (id: string) => `/customer-groups/${encodeURIComponent(id)}`;

/** Server-side sort keys: CustomerRow field names, plus the profile's average days to pay. */
export type CustomerSort =
  | "overdue_total"
  | "outstanding_total"
  | "oldest_overdue_days"
  | "last_payment_on"
  | "avg_days_to_pay"
  | "display_name";
export type SortDir = "asc" | "desc";
export type CustomerListQuery = { sort: CustomerSort; dir: SortDir };
export type CustomerBook = { customers: CustomerRow[]; groups: CustomerGroupRow[] };

/**
 * The UI's sort names are row field names; GET /customers takes its own four
 * keys and fixes the direction that reads naturally for each (money largest
 * first, names A-Z). Anything the server does not offer is served by the closest
 * key and the requested direction is applied to the rows it returns -- an
 * ordering of figures the server sent, never a sum.
 */
const SERVER_SORT: Record<CustomerSort, { sort: "outstanding" | "overdue" | "avg_days" | "name"; dir: SortDir }> = {
  outstanding_total: { sort: "outstanding", dir: "desc" },
  overdue_total: { sort: "overdue", dir: "desc" },
  avg_days_to_pay: { sort: "avg_days", dir: "desc" },
  display_name: { sort: "name", dir: "asc" },
  oldest_overdue_days: { sort: "overdue", dir: "desc" },
  last_payment_on: { sort: "name", dir: "asc" },
};

/**
 * GET /customers?sort=&group=true: every customer row, sorted by the server,
 * with the owner's groups. A grouped entry carries its members nested, so they
 * are flattened back into `customers` (each keeps its own `group_id`), which is
 * what `sectionRows` expects. Offline: the saved sample rows, ordered by
 * `sortSampleRows`.
 */
export function listCustomers(q: CustomerListQuery): Promise<Sourced<CustomerBook>> {
  const server = SERVER_SORT[q.sort] ?? SERVER_SORT.outstanding_total;
  return v12OrSample(
    async () => {
      const body = await call<{
        entries?: {
          kind: string;
          customer?: CustomerRow | null;
          group?: CustomerGroupRow | null;
        }[];
      }>(`/customers?sort=${server.sort}&group=true`);
      const entries = body.entries ?? [];
      const customers: CustomerRow[] = [];
      const groups: CustomerGroupRow[] = [];
      for (const entry of entries) {
        if (entry.kind === "GROUP" && entry.group) {
          groups.push(entry.group);
          for (const member of entry.group.members ?? []) {
            customers.push({ ...member, group_id: member.group_id ?? entry.group.id, group_label: member.group_label ?? entry.group.label });
          }
          continue;
        }
        if (entry.customer) {
          const row = entry.customer;
          customers.push(row);
          if (row.group_id && !groups.some((g) => g.id === row.group_id)) {
            // A row can name a group the list did not send; keep the label it carries.
            groups.push({
              id: row.group_id,
              label: row.group_label ?? row.group_id,
              created_at: "",
              created_by: "",
              member_count: 0,
            });
          }
        }
      }
      const rows = q.dir === server.dir ? customers : [...customers].reverse();
      return { customers: rows, groups };
    },
    () => {
      const sample = offlineCustomerRows();
      return sample ? { customers: sortSampleRows(sample, q.sort, q.dir), groups: offlineCustomerGroups() ?? [] } : null;
    },
  );
}

/** GET /customers/{id}: identity, group, stats, payments, suggestions and cases. */
export function getCustomer(id: string): Promise<Sourced<CustomerProfile>> {
  return v12OrSample(
    async () => {
      const body = await call<CustomerProfile>(customerUrl(id));
      if (typeof body?.customer?.id !== "string" || typeof body?.stats !== "object") {
        throw new ApiError(500, "BAD_RESPONSE", "The customer did not match the contract.");
      }
      return body;
    },
    // The one sample profile stands in only for its own sample customer.
    () => {
      const sample = offlineCustomerProfile();
      return sample?.customer.id === id ? sample : null;
    },
  );
}

/** GET /customers/suggestions: possible same-buyer pairs. A suggestion never merges anything by itself. */
export function listSuggestions(): Promise<Sourced<Suggestion[]>> {
  return v12OrSample(async () => listOf<Suggestion>(await call<unknown>("/customers/suggestions"), "suggestions"), offlineSuggestions);
}

/** GET /insights: portfolio totals and charts, as the server computed them. */
export function getInsights(): Promise<Sourced<PortfolioInsights>> {
  return v12OrSample(
    async () => {
      const body = await call<PortfolioInsights>("/insights");
      if (typeof body?.as_of !== "string") throw new ApiError(500, "BAD_RESPONSE", "The insights did not match the contract.");
      return body;
    },
    offlinePortfolioInsights,
  );
}

/** GET /cases/{id}/payments (PaymentListResponse), voided ones included (they carry `voided_at`). */
export function listPayments(caseId: string): Promise<Sourced<Payment[]>> {
  return v12OrSample(async () => (await call<PaymentListResponse>(`${caseUrl(caseId)}/payments`)).payments ?? [], offlinePayments);
}

// Identity: every change below is audited by the server and has an undo.

/** Add a GSTIN to a customer. Undo: `detachGstin`. */
export function attachGstin(customerId: string, gstin: string, opts: MutationOptions): Promise<void> {
  return mutateVoid(`${customerUrl(customerId)}/gstins`, opts, { gstin });
}

export function detachGstin(customerId: string, gstin: string, opts: MutationOptions): Promise<void> {
  return mutateVoid(`${customerUrl(customerId)}/gstins/${encodeURIComponent(gstin)}`, opts, undefined, "DELETE");
}

/**
 * Accept an ATTACH suggestion: the provisional customer `sourceId` joins the
 * PAN customer `targetId`, whose PAN stays the legal identity. The provisional
 * record keeps existing with no invoices, so the move can be undone. Different
 * PANs are never merged; the server refuses that. Undo: `detachCustomer`.
 */
export function attachCustomer(targetId: string, sourceId: string, opts: MutationOptions): Promise<void> {
  // The route hangs off the provisional side: POST /customers/{provisional}/attach
  return mutateVoid(`${customerUrl(sourceId)}/attach`, opts, { target_customer_id: targetId });
}

/** Undo an attach: the server moves back everything that attach took from `sourceId`. */
export function detachCustomer(targetId: string, sourceId: string, opts: MutationOptions): Promise<void> {
  return mutateVoid(`${customerUrl(targetId)}/detach`, opts, { restore_customer_id: sourceId });
}

/** A group links customers for viewing together; each keeps its own legal identity and cases. */
export function createGroup(label: string, customerIds: string[], opts: MutationOptions): Promise<CustomerGroupRow> {
  return mutate<CustomerGroupRow>("/customer-groups", opts, { label, customer_ids: customerIds });
}

export function linkToGroup(groupId: string, customerId: string, opts: MutationOptions): Promise<void> {
  return mutateVoid(`${groupUrl(groupId)}/members`, opts, { customer_id: customerId });
}

export function unlinkFromGroup(groupId: string, customerId: string, opts: MutationOptions): Promise<void> {
  return mutateVoid(`${groupUrl(groupId)}/members/${encodeURIComponent(customerId)}`, opts, undefined, "DELETE");
}

/** "Not the same buyer": hide this suggestion. Undo: `undoDismissSuggestion`. */
export function dismissSuggestion(a: string, b: string, opts: MutationOptions): Promise<void> {
  return mutateVoid("/customers/suggestions/dismiss", opts, { a, b });
}

export function undoDismissSuggestion(a: string, b: string, opts: MutationOptions): Promise<void> {
  return mutateVoid("/customers/suggestions/undo-dismiss", opts, { a, b });
}

// Payments (shipped routes): what the owner says they received. `amount` is the
// decimal string the owner typed, passed through untouched; the server
// validates it and re-evaluates the case, answering with the refreshed CaseDetail.

export type PaymentInput = PaymentCreateRequest;

export function recordPayment(caseId: string, input: PaymentInput, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(caseId)}/payments`, opts, input);
}

/** Voiding keeps the row (with `voided_at`) so the record stays auditable. The route takes no body. */
export function voidPayment(caseId: string, paymentId: string, opts: MutationOptions): Promise<CaseDetail> {
  return mutate<CaseDetail>(`${caseUrl(caseId)}/payments/${encodeURIComponent(paymentId)}/void`, opts);
}

// CSV import: preview first, nothing is stored until the owner confirms.
//
// The server is stateless on purpose: the preview returns an `import_token` that
// signs the exact bytes it read, and the commit must send the same file back
// with that token. The browser keeps the chosen file in memory under the token,
// so the owner confirms what they just saw and no staging copy exists anywhere.

type RawImportRow = {
  row_no: number;
  status: string;
  parsed: {
    invoice_no: string;
    invoice_date: string;
    delivery_date: string;
    amount: string;
    buyer_name: string;
    buyer_gstin?: string | null;
    agreed_credit_days?: number | null;
    paid_on?: string | null;
    paid_amount?: string | null;
    notes?: string | null;
  } | null;
  customer_match: {
    customer_id?: string | null;
    display_name?: string | null;
    matched_on: string;
    would_create: boolean;
    warnings?: string[];
  } | null;
  errors: string[];
  warnings: string[];
  case_id?: string | null;
  payment_id?: string | null;
};

type RawImportSummary = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  created_rows: number;
  skipped_rows: number;
  failed_rows: number;
  payments_created: number;
  date_format: string;
  errors?: string[];
  warnings?: string[];
};

type RawImportResponse = {
  filename: string;
  import_token: string;
  rows: RawImportRow[];
  summary: RawImportSummary;
  created_case_ids?: string[];
  skipped?: string[];
};

export const IMPORT_COLUMNS = [
  "invoice_no",
  "invoice_date",
  "delivery_date",
  "amount",
  "buyer_name",
  "buyer_gstin",
  "agreed_credit_days",
  "paid_on",
  "paid_amount",
  "notes",
] as const;

const pendingImports = new Map<string, { file: Blob; filename: string }>();

function rowCells(row: RawImportRow): Record<string, string> {
  const p = row.parsed;
  if (!p) return {};
  return {
    invoice_no: p.invoice_no,
    invoice_date: p.invoice_date,
    delivery_date: p.delivery_date,
    amount: p.amount,
    buyer_name: p.buyer_name,
    buyer_gstin: p.buyer_gstin ?? "",
    agreed_credit_days: p.agreed_credit_days == null ? "" : String(p.agreed_credit_days),
    paid_on: p.paid_on ?? "",
    paid_amount: p.paid_amount ?? "",
    notes: p.notes ?? "",
  };
}

/** The server's per-row verdicts, in the additive shape `importRows.ts` reads (CR-20). */
function rowViews(rows: RawImportRow[]) {
  return rows.map((row) => {
    const match = row.customer_match;
    const kind = !match ? "unknown" : match.customer_id ? "existing" : match.matched_on === "NEW" ? "new" : "provisional";
    return {
      row: row.row_no,
      status: row.errors.length ? "error" : row.warnings.length ? "warning" : "ready",
      message: row.errors[0] ?? row.warnings[0] ?? null,
      match: {
        kind,
        customer_name: match?.display_name ?? null,
        customer_id: match?.customer_id ?? null,
      },
      cells: rowCells(row),
    };
  });
}

function toImportPreview(body: RawImportResponse): ImportPreview {
  const views = rowViews(body.rows);
  return {
    preview_id: body.import_token,
    filename: body.filename,
    total_rows: body.summary.total_rows,
    valid_rows: body.summary.valid_rows,
    invalid_rows: body.summary.invalid_rows,
    requires_confirmation: true,
    columns: [...IMPORT_COLUMNS],
    sample_rows: views
      .filter((v) => v.status !== "error")
      .slice(0, 20)
      .map((v) => v.cells),
    errors: [
      ...(body.summary.errors ?? []),
      ...views.filter((v) => v.status === "error").map((v) => `Row ${v.row}: ${v.message ?? "check this row"}`),
    ],
    warnings: body.summary.warnings ?? [],
    // Additive: the per-row table, which the preview screen prefers when present.
    rows: views,
  } as ImportPreview;
}

function toImportResult(body: RawImportResponse, previewId: string): ImportResult {
  const created = body.rows.filter((r) => r.status === "CREATED");
  const customerIds = [...new Set(created.map((r) => r.customer_match?.customer_id).filter((id): id is string => Boolean(id)))];
  return {
    preview_id: previewId,
    imported: body.summary.created_rows,
    skipped: body.summary.skipped_rows,
    failed: body.summary.failed_rows,
    customers_created: created.filter((r) => r.customer_match?.would_create).length,
    customers_matched: created.filter((r) => r.customer_match?.customer_id).length,
    gstins_attached: 0,
    case_ids: body.created_case_ids ?? [],
    errors: [
      ...(body.summary.errors ?? []),
      ...created.flatMap((r) => r.errors.map((e) => `Row ${r.row_no}: ${e}`)),
    ],
    warnings: body.summary.warnings ?? [],
    // Additive: the customer ids of rows that landed on an existing customer.
    customer_ids: customerIds,
  } as ImportResult;
}

export async function previewImport(file: Blob, filename: string, opts: MutationOptions): Promise<ImportPreview> {
  const form = new FormData();
  form.append("file", file, filename);
  const body = await call<RawImportResponse>("/import/invoices?mode=preview", {
    method: "POST",
    headers: { "Idempotency-Key": opts.idempotencyKey },
    body: form,
  });
  if (typeof body?.import_token !== "string") throw new ApiError(500, "BAD_RESPONSE", "The import preview did not match the contract.");
  pendingImports.set(body.import_token, { file, filename });
  return toImportPreview(body);
}

export async function confirmImport(previewId: string, opts: MutationOptions): Promise<ImportResult> {
  const pending = pendingImports.get(previewId);
  if (!pending) {
    throw new ApiError(
      409,
      "PREVIEW_EXPIRED",
      "This preview is no longer in this browser. Preview the file again, then confirm.",
    );
  }
  const form = new FormData();
  form.append("file", pending.file, pending.filename);
  const body = await call<RawImportResponse>(
    `/import/invoices?mode=commit&import_token=${encodeURIComponent(previewId)}`,
    { method: "POST", headers: { "Idempotency-Key": opts.idempotencyKey }, body: form },
  );
  pendingImports.delete(previewId);
  return toImportResult(body, previewId);
}
