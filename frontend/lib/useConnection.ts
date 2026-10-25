"use client";

// Backend reachability for the top-bar status pill. This only reports whether
// the engine answered /health; it never decides which numbers to show (each
// screen's own evaluation does that, falling back to saved fixtures offline).

import { useEffect, useState } from "react";
import { health } from "./api";

export type Connection = "checking" | "live" | "offline";

const POLL_MS = 20_000;

export function useConnection(): Connection {
  const [state, setState] = useState<Connection>("checking");
  useEffect(() => {
    let alive = true;
    const check = () => health().then((ok) => alive && setState(ok ? "live" : "offline"));
    check();
    const id = setInterval(check, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return state;
}

/** Lets any button open the judge console without prop drilling. */
export const JUDGE_EVENT = "samaadhan:toggle-judge";
