"use client";

import { markRecoverySent, startRecovery } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { awaitingSent, canPrepare, recoveryStatus } from "@/lib/recoveryFlow";
import type { Stage } from "@/lib/types";
import type { TrackView } from "@/lib/useTrack";
import { IdempotentButton } from "../common/IdempotentButton";
import { RecoveryBadge } from "../common/RecoveryBadge";

/**
 * Under a draft: record that the owner prepared the step, and later that they
 * sent it themselves. The app sends nothing; "I've sent it" only records what the
 * owner says, and appears once they have opened WhatsApp or email or copied the draft.
 */
export function RecoveryActions({
  caseId,
  stage,
  tracking,
  used,
}: {
  caseId: string;
  stage: Stage;
  tracking: TrackView;
  /** The owner opened WhatsApp or email or copied the draft for this stage. */
  used: boolean;
}) {
  const { t } = useT();
  const track = tracking.track;
  const status = recoveryStatus(track, stage);
  const offline = tracking.source === "offline";
  const actions = tracking.caseDetail?.available_actions ?? [];

  return (
    <section aria-label={t("recovery.title")} className="flex flex-col gap-3 rounded-lg border border-rule bg-paper px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium text-ink-950">{t("recovery.title")}</h3>
        <RecoveryBadge status={status} />
      </div>

      {status === "none" && canPrepare(track, actions) && (
        <div className="flex flex-col gap-1.5">
          <div>
            <IdempotentButton
              actionId={`recovery.prepare:${caseId}:${stage}`}
              run={async (opts) => {
                await startRecovery(caseId, stage, opts);
                await tracking.refresh();
              }}
              version={tracking.version}
              onConflict={tracking.refresh}
              offline={offline}
              className="btn btn-secondary"
            >
              {t("recovery.prepare")}
            </IdempotentButton>
          </div>
          <p className="text-xs text-ink-500">{t("recovery.prepare_hint")}</p>
        </div>
      )}

      {awaitingSent(track, stage) && (
        <div className="flex flex-col gap-1.5">
          {used ? (
            <div>
              <IdempotentButton
                actionId={`recovery.sent:${caseId}:${stage}`}
                run={async (opts) => {
                  await markRecoverySent(caseId, opts);
                  await tracking.refresh();
                }}
                version={tracking.version}
                onConflict={tracking.refresh}
                offline={offline}
              >
                {t("recovery.mark_sent")}
              </IdempotentButton>
            </div>
          ) : (
            <p className="text-xs text-ink-500">{t("recovery.use_first")}</p>
          )}
          {used && <p className="text-xs text-ink-500">{t("recovery.mark_hint")}</p>}
        </div>
      )}
    </section>
  );
}
