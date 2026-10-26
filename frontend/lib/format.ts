// Formatting only (AGENTS.md golden rule 6). Every input is a decimal string or
// ISO date string from the API. Nothing here rounds, converts to float, or
// derives a legal value; it only re-groups digits and spells out dates.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Indian digit grouping of an integer digit string: 1250000 -> 12,50,000. */
function groupIndian(intDigits: string): string {
  if (intDigits.length <= 3) return intDigits;
  const last3 = intDigits.slice(-3);
  let rest = intDigits.slice(0, -3);
  const parts: string[] = [];
  while (rest.length > 2) {
    parts.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  if (rest) parts.unshift(rest);
  return `${parts.join(",")},${last3}`;
}

function splitDecimal(value: string): { neg: boolean; int: string; frac: string } | null {
  const m = /^(-)?(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!m) return null;
  return { neg: Boolean(m[1]), int: m[2].replace(/^0+(?=\d)/, ""), frac: m[3] ?? "" };
}

/**
 * Rupees with Indian grouping. "1250000.00" -> "₹12,50,000.00".
 * `paise: "auto"` hides the fraction only when it is exactly zero (display
 * choice, no rounding).
 */
export function money(value: string | null | undefined, opts: { paise?: "always" | "auto" } = {}): string {
  if (value === null || value === undefined) return "—";
  const p = splitDecimal(value);
  if (!p) return value;
  const frac = p.frac.padEnd(2, "0");
  const showFrac = opts.paise === "auto" ? !/^0*$/.test(frac) : true;
  return `${p.neg ? "−" : ""}₹${groupIndian(p.int)}${showFrac ? `.${frac}` : ""}`;
}

/** Splits a money string for hero display: { whole: "₹3,00,000", paise: ".00" }. */
export function moneyParts(value: string | null | undefined): { whole: string; paise: string } {
  if (value === null || value === undefined) return { whole: "—", paise: "" };
  const p = splitDecimal(value);
  if (!p) return { whole: value, paise: "" };
  return { whole: `${p.neg ? "−" : ""}₹${groupIndian(p.int)}`, paise: `.${p.frac.padEnd(2, "0")}` };
}

/** "16.50" -> "16.50%". The value is shown exactly as the engine sent it. */
export function pct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value}%`;
}

/** "2026-01-10" -> "10 Jan 2026". Parsed as text, so no timezone shifts. */
export function date(value: string | null | undefined): string {
  if (!value) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return value;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? m[2]} ${m[1]}`;
}

/** A server day count such as "48.67" shown as "49" next to a "~". Days, never money. */
export function approxDays(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? count(Math.round(n)) : value;
}

/** Plain integer with Indian grouping (counts, days). */
export function count(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n < 0 ? "−" : ""}${groupIndian(String(Math.trunc(Math.abs(n))))}`;
}

/**
 * Converts a decimal money string to integer paise for the live ticker only.
 * Exact (BigInt), no float. Extra fraction digits beyond 2 are dropped for
 * display; the engine's own figures are always shown as sent.
 */
export function toPaise(value: string): bigint | null {
  const p = splitDecimal(value);
  if (!p) return null;
  const v = BigInt(p.int) * BigInt(100) + BigInt((p.frac + "00").slice(0, 2));
  return p.neg ? -v : v;
}

/** Integer paise -> money string with Indian grouping. */
export function paiseToMoney(paise: bigint): string {
  const neg = paise < BigInt(0);
  const abs = neg ? -paise : paise;
  const int = (abs / BigInt(100)).toString();
  const frac = (abs % BigInt(100)).toString().padStart(2, "0");
  return money(`${neg ? "-" : ""}${int}.${frac}`);
}
