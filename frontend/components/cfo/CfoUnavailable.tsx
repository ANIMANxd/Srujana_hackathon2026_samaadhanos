"use client";

import Link from "next/link";
import { isNotCovered } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { EligibilityPill } from "../case/EligibilityPill";

/**
 * The CFO view when the engine returned no buyer-cost lines: say why, plainly,
 * instead of showing zeros or an estimate (golden rule 7).
 */
export function CfoUnavailable({ caseId, response }: { caseId: string; response: CaseResponse }) {
  const { t } = useT();
  const href = useHref();
  const blocked = isNotCovered(response);
  const reason = blocked ? "GATE" : response.timeline?.objection_status === "NO_DELIVERY_PROOF" ? "NO_DELIVERY_PROOF" : "GENERIC";
  return (
    <section aria-labelledby="cfo-na" className="panel flex flex-col items-start gap-4 p-6 sm:p-8">
      <EligibilityPill status={response.jurisdiction.status} />
      <h2 id="cfo-na" className="text-xl font-semibold tracking-[-0.015em] text-ink-950">{t("cfo.unavailable.title")}</h2>
      <p className="max-w-2xl text-sm leading-relaxed text-ink-700">{t(`cfo.unavailable.${reason}`)}</p>
      {blocked && (
        <Link href={href(`/eligibility/${caseId}`)} className="btn btn-secondary">
          {t("cfo.unavailable.see_why")}
          <Icon name="arrow-right" className="h-4 w-4" />
        </Link>
      )}
    </section>
  );
}
