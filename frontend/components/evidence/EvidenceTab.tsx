"use client";

import type { CaseRequest, CaseResponse } from "@/lib/types";
import { DefensesPanel } from "./DefensesPanel";
import { EvidenceLocker } from "./EvidenceLocker";
import { LimitationClock } from "./LimitationClock";
import { ReadinessGauge } from "./ReadinessGauge";
import { TimelineDetail } from "./TimelineDetail";

/**
 * Evidence & timeline tab (?tab=evidence): what you hold on the left, what the
 * engine made of it on the right. Edits in the locker re-evaluate the case.
 */
export function EvidenceTab({
  caseId,
  request,
  base,
  response,
  onChange,
}: {
  caseId: string;
  request: CaseRequest;
  base: CaseRequest;
  response: CaseResponse;
  onChange: (next: CaseRequest) => void;
}) {
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[1.1fr_1fr]">
      <div className="flex flex-col gap-4">
        <EvidenceLocker request={request} base={base} response={response} onChange={onChange} />
        <DefensesPanel defenses={response.defenses} />
      </div>
      <div className="flex flex-col gap-4">
        <ReadinessGauge caseId={caseId} response={response} />
        <TimelineDetail request={request} response={response} />
        <LimitationClock limitation={response.limitation} />
      </div>
    </div>
  );
}
