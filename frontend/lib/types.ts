// Contract v1.0/v1.1 types, re-exported under short names. The source of truth is
// ../contracts/types.ts (copied to generated/ by scripts/sync-contracts.mjs).
// Never hand-edit a contract shape here; request an additive change instead
// (see CONTRACT-REQUESTS.md).

import type { components } from "@/generated/contract-types";

type S = components["schemas"];

export type CaseRequest = S["CaseEvaluationRequest"];
export type CaseResponse = S["CaseEvaluationResponse"];
export type Jurisdiction = S["Jurisdiction"];
export type JurisdictionStatus = S["JurisdictionStatus"];
export type Timeline = S["Timeline"];
export type Financials = S["Financials"];
export type LedgerRow = S["LedgerRow"];
export type RateSegment = S["RateSegment"];
export type BuyerCost = S["BuyerCost"];
export type Limitation = S["Limitation"];
export type LimitationStatus = S["LimitationStatus"];
export type Defense = S["Defense"];
export type DefenseStatus = S["DefenseStatus"];
export type EvidenceReadiness = S["EvidenceReadiness"];
export type ReadinessBand = S["ReadinessBand"];
export type Citation = S["Citation"];
export type ApiWarning = S["Warning"];
export type EvidenceKind = S["EvidenceKind"];
export type EvidenceItem = S["EvidenceItem"];
export type EnterpriseClass = S["EnterpriseClass"];
export type Activity = S["Activity"];
export type RateMode = S["RateMode"];
export type AppropriationMode = S["AppropriationMode"];
export type PartPayment = S["PartPayment"];
export type Objection = S["Objection"];
export type ArtifactKind = S["ArtifactKind"];
export type ArtifactResponse = S["ArtifactResponse"];
export type ExtractionResponse = S["ExtractionResponse"];
export type ExtractedField = S["ExtractedField"];
export type ExtractedMessage = S["ExtractedMessage"];
export type ExtractionMethod = S["ExtractionMethod"];
export type MessageTag = S["MessageTag"];
export type SourceKind = S["SourceKind"];
export type SettlementSimulationResponse = S["SettlementSimulationResponse"];
export type SettlementPayment = S["SettlementPayment"];

// Contract v1.1 (persistent cases, tracks, two options).
export type StoredCase = S["Case"];
export type CaseDetail = S["CaseDetail"];
export type Track = S["Track"];
export type TrackKind = S["TrackKind"];
export type TrackState = S["TrackState"];
export type OptionsResponse = S["OptionsResponse"];
export type OptionCitation = S["OptionCitation"];
export type CaseSummary = S["CaseSummary"];
export type WebhookDelivery = S["WebhookDelivery"];
export type FinancingActionResponse = S["FinancingActionResponse"];
export type RecoveryActionResponse = S["RecoveryActionResponse"];
export type Bid = S["Bid"];
export type ESignSession = S["ESignSession"];
export type PayoutStatus = S["PayoutStatus"];
export type AuditEvent = S["Event"];
export type ChainVerifyResult = S["ChainVerifyResult"];

// Contract v1.2 (customer book). Descriptive figures from the owner's own data only.
export type Customer = S["Customer"];
export type CustomerKind = S["CustomerKind"];
export type CustomerRow = S["CustomerRow"];
export type CustomerGroupRow = S["CustomerGroupRow"];
export type CustomerProfile = S["CustomerProfile"];
export type CustomerStats = S["CustomerStats"];
export type ChartSeriesPoint = S["ChartSeriesPoint"];
export type Payment = S["Payment"];
export type PaymentMethod = S["PaymentMethod"];
export type PaymentCreateRequest = S["PaymentCreateRequest"];
export type PaymentListResponse = S["PaymentListResponse"];
export type Suggestion = S["Suggestion"];
export type SuggestionKind = S["SuggestionKind"];
export type ImportPreview = S["ImportPreview"];
export type ImportResult = S["ImportResult"];
export type PortfolioInsights = S["PortfolioInsights"];

export type ConfigEntry = {
  value: unknown;
  source_ref: string;
  verified: boolean;
  note: string;
};

/** GET /api/v1/config: the raw statute config (or a labelled stub, CQ-1). */
export type StatuteConfig = Record<string, ConfigEntry | unknown>;

/** GET /api/v1/presets (CQ-2). */
export type PresetSummary = { id: string; title: string };

/** Escalation stages 1-4 (architecture.md 5.5 / spec 5.5). */
export type Stage = 1 | 2 | 3 | 4;
export const STAGES: Stage[] = [1, 2, 3, 4];

export function isConfigEntry(v: unknown): v is ConfigEntry {
  return (
    typeof v === "object" &&
    v !== null &&
    "value" in v &&
    "verified" in v &&
    typeof (v as { verified: unknown }).verified === "boolean"
  );
}
