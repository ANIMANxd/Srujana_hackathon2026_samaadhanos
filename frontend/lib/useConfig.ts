"use client";

// GET /api/v1/config for the assumptions drawer and section-chip explanations.
// Values are shown as the config holds them, with their verified flags.

import { useEffect, useState } from "react";
import { getConfig } from "./api";
import { isConfigEntry, type ConfigEntry, type StatuteConfig } from "./types";

let cache: Promise<StatuteConfig | null> | null = null;

function load(): Promise<StatuteConfig | null> {
  if (!cache) {
    cache = getConfig().then((c) => {
      if (c === null) cache = null; // retry on next mount when the backend comes back
      return c;
    });
  }
  return cache;
}

export type ConfigState = { config: StatuteConfig | null; loading: boolean; isStub: boolean };

export function useConfig(): ConfigState {
  const [state, setState] = useState<ConfigState>({ config: null, loading: true, isStub: false });
  useEffect(() => {
    let alive = true;
    load().then((config) => {
      if (alive) setState({ config, loading: false, isStub: Boolean(config && config["_stub"] === true) });
    });
    return () => {
      alive = false;
    };
  }, []);
  return state;
}

export function configEntry(config: StatuteConfig | null, key: string): ConfigEntry | null {
  const v = config?.[key];
  return isConfigEntry(v) ? v : null;
}

/** A scalar config value as display text, or null if absent. Never used for math. */
export function configText(config: StatuteConfig | null, key: string): string | null {
  const e = configEntry(config, key);
  if (!e || e.value === null || e.value === undefined) return null;
  return typeof e.value === "string" || typeof e.value === "number" ? String(e.value) : null;
}
