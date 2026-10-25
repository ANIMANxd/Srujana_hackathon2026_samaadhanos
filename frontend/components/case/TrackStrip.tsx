"use client";

import { useT } from "@/lib/i18n";
import type { TrackView } from "@/lib/useTrack";
import { Icon } from "../common/Icon";
import { Banner } from "../shell/Banners";

/**
 * Where a stored case stands: which option (if any) is active and how updates
 * arrive. Offline it says plainly that the case on screen is a saved sample.
 * The option steps themselves belong to the early and recovery flows.
 */
export function TrackStrip({ tracking }: { tracking: TrackView }) {
  const { t } = useT();
  if (!tracking.caseDetail) return null;
  const offline = tracking.source === "offline";
  const kind = tracking.track?.kind;
  return (
    <div className="no-print flex flex-col gap-2">
      {offline && <Banner tone="warn" icon="lock" message="track.offline_sample" />}
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-600">
        <span>{kind ? t(`track.option.${kind}`) : t("track.option.none")}</span>
        <span className="inline-flex items-center gap-1.5">
          <Icon name="info" className="h-3.5 w-3.5" />
          {tracking.live === "stream" ? t("track.live_stream") : tracking.live === "polling" ? t("track.live_polling") : t("track.live_off")}
        </span>
      </p>
    </div>
  );
}
