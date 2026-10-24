// Small hand-drawn icon set for the product's own concepts (status, ledger,
// clock, document). Icons are decorative: meaning is always carried by text.

export type IconName =
  | "ok"
  | "warn"
  | "block"
  | "info"
  | "open"
  | "clock"
  | "ledger"
  | "doc"
  | "send"
  | "copy"
  | "upload"
  | "arrow-right"
  | "arrow-left"
  | "close"
  | "chevron"
  | "lock"
  | "spark";

const PATHS: Record<IconName, string> = {
  ok: "M4 10.5l3.5 3.5L16 5.5",
  warn: "M10 3l7.5 13h-15L10 3zM10 8v4M10 14.5v.01",
  block: "M5 5l10 10M15 5L5 15",
  info: "M10 9v5M10 6v.01M10 18a8 8 0 100-16 8 8 0 000 16z",
  open: "M7.5 7.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2M10 14.5v.01M10 18a8 8 0 100-16 8 8 0 000 16z",
  clock: "M10 5.5V10l3 2M10 18a8 8 0 100-16 8 8 0 000 16z",
  ledger: "M4 3h10l2 2v12H4V3zM7 7h6M7 10h6M7 13h4",
  doc: "M5 2.5h7l3 3v12H5v-15zM12 2.5v3h3M8 9h5M8 12h5",
  send: "M3 10l14-6-5 14-2.5-5.5L3 10z",
  copy: "M7 7h9v10H7V7zM4 13V3h9",
  upload: "M10 13V3M6 7l4-4 4 4M4 13v4h12v-4",
  "arrow-right": "M4 10h12M11 5l5 5-5 5",
  "arrow-left": "M16 10H4M9 5l-5 5 5 5",
  close: "M5 5l10 10M15 5L5 15",
  chevron: "M7 5l5 5-5 5",
  lock: "M5 9h10v8H5V9zM7 9V6.5a3 3 0 016 0V9",
  spark: "M10 2v4M10 14v4M2 10h4M14 10h4",
};

export function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
