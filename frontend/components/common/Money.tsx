import { money, moneyParts } from "@/lib/format";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

/** An engine money string, Indian-grouped, with a placeholder badge when needed. */
export function Money({
  value,
  placeholder = false,
  hero = false,
  className = "",
}: {
  value: string | null | undefined;
  placeholder?: boolean;
  hero?: boolean;
  className?: string;
}) {
  if (hero) {
    const p = moneyParts(value);
    return (
      <span className={`num inline-flex items-baseline gap-1 ${className}`}>
        <span>{p.whole}</span>
        <span className="text-[0.55em] text-ink-500">{p.paise}</span>
        {placeholder && <PlaceholderBadge />}
      </span>
    );
  }
  return (
    <span className={`num inline-flex items-baseline gap-1.5 ${className}`}>
      <span>{money(value)}</span>
      {placeholder && <PlaceholderBadge />}
    </span>
  );
}
