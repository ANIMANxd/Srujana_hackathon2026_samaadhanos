import type { Tone } from "@/lib/derive";
import { Icon, type IconName } from "./Icon";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-ok-wash text-ok",
  warn: "bg-warn-wash text-warn",
  block: "bg-block-wash text-block",
  info: "bg-info-wash text-info",
};

const TONE_ICON: Record<Tone, IconName> = { ok: "ok", warn: "warn", block: "block", info: "info" };

/** Status = icon + text, never colour alone (AGENTS.md §5). */
export function StatusIcon({
  tone,
  label,
  icon,
  size = "md",
  wrap = false,
}: {
  tone: Tone;
  label: string;
  icon?: IconName;
  size?: "sm" | "md";
  /** Let a long label wrap inside the pill (used in narrow table cells). */
  wrap?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ${TONE_CLASS[tone]} ${
        size === "sm" ? "min-h-6 px-2 text-xs" : "min-h-7 px-2.5 text-[0.8125rem]"
      } ${wrap ? "max-w-full py-0.5" : ""}`}
    >
      <Icon name={icon ?? TONE_ICON[tone]} className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      <span className={wrap ? "text-left leading-snug whitespace-normal" : "whitespace-nowrap"}>{label}</span>
    </span>
  );
}
