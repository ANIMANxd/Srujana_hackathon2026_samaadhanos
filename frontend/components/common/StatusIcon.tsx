import type { Tone } from "@/lib/derive";
import { Icon, type IconName } from "./Icon";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-ok-wash text-ok border-ok/30",
  warn: "bg-warn-wash text-warn border-warn/30",
  block: "bg-block-wash text-block border-block/30",
  info: "bg-info-wash text-info border-info/30",
};

const TONE_ICON: Record<Tone, IconName> = { ok: "ok", warn: "warn", block: "block", info: "info" };

/** Status = icon + text, never colour alone (AGENTS.md §5). */
export function StatusIcon({
  tone,
  label,
  icon,
  size = "md",
}: {
  tone: Tone;
  label: string;
  icon?: IconName;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border font-semibold ${TONE_CLASS[tone]} ${
        size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2.5 py-1 text-sm"
      }`}
    >
      <Icon name={icon ?? TONE_ICON[tone]} className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      <span>{label}</span>
    </span>
  );
}
