"use client";

import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";

/**
 * "What this means for you" (architecture §10: one plain-language card per
 * block), keyed by the engine's own code in i18n: `meaning.<block>.<code>`.
 * An unknown code renders nothing rather than guessing.
 */
export function Meaning({ block, code }: { block: string; code: string }) {
  const { t, tCode } = useT();
  const text = tCode(`meaning.${block}`, code, "");
  if (!text) return null;
  return (
    <div className="flex gap-3 rounded-lg bg-paper px-4 py-3">
      <Icon name="info" className="mt-0.5 h-4 w-4 text-saffron-600" />
      <div className="flex flex-col gap-0.5">
        <span className="eyebrow">{t("meaning.label")}</span>
        <p className="text-sm leading-relaxed text-ink-800">{text}</p>
      </div>
    </div>
  );
}
