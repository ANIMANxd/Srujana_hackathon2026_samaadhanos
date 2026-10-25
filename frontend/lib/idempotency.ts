// One Idempotency-Key per user action (architecture_v4 §8). A key is minted
// the first time an action runs and handed out again while that same action
// is retried (a dropped connection, a 5xx), so the server can replay instead
// of doing it twice. Once the action has a definite answer the key is released
// and the next click is a new action with a new key.

const active = new Map<string, string>();

function newKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // Non-secure contexts (plain http on a LAN demo laptop) have no randomUUID.
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined") crypto.getRandomValues(bytes);
  else bytes.forEach((_, i) => (bytes[i] = Math.floor(Math.random() * 256)));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * The key for this action: the one already in flight, or a fresh one.
 * `actionId` names the action AND its payload (e.g. `financing.cancel:<case>`);
 * a different body must use a different id, because the server answers 409
 * to the same key with a different body.
 */
export function idempotencyKeyFor(actionId: string): string {
  const existing = active.get(actionId);
  if (existing) return existing;
  const key = newKey();
  active.set(actionId, key);
  return key;
}

/** The action got a definite answer; the next attempt is a new action. */
export function releaseIdempotencyKey(actionId: string): void {
  active.delete(actionId);
}
