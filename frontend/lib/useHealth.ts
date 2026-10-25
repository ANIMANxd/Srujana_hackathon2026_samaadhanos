"use client";

// Whether the backend says it is a production deployment. The judge console
// and its mock controls must not exist there (architecture_v4 section 8):
// `app_env` is the field the API is asked to report; `provider_mode: live`
// (no mock providers) counts as production too. An unreachable backend is not
// production: the local rehearsal tools still work offline.

import { useEffect, useState } from "react";
import { getHealth } from "./api";

export function isProductionHealth(h: Record<string, string> | null): boolean {
  if (!h) return false;
  const env = (h.app_env ?? h.environment ?? h.mode ?? "").toLowerCase();
  return env === "production" || h.provider_mode?.toLowerCase() === "live";
}

export function useProductionMode(): boolean {
  const [prod, setProd] = useState(false);
  useEffect(() => {
    let alive = true;
    getHealth().then((h) => {
      if (alive) setProd(isProductionHealth(h));
    });
    return () => {
      alive = false;
    };
  }, []);
  return prod;
}
