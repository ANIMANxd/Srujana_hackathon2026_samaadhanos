"use client";

import { useRef, type KeyboardEvent } from "react";
import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";
import type { AppropriationMode, CaseRequest, CaseResponse, RateMode } from "@/lib/types";

const MODES: RateMode[] = ["FLOATING", "FROZEN_AT_APPOINTED_DAY"];
const APPS: AppropriationMode[] = ["INTEREST_FIRST", "PRINCIPAL_FIRST"];

/** The engine's own sentence about a choice, picked by its opening words (it states the mode it used). */
function engineSays(res: CaseResponse, prefix: string): string | null {
  return res.assumptions.find((a) => a.startsWith(prefix)) ?? null;
}

function Toggle<T extends string>({
  label,
  options,
  value,
  optionKey,
  overridden,
  onPick,
  onDefault,
  note,
}: {
  label: string;
  options: T[];
  value: T;
  optionKey: (v: T) => MessageKey;
  overridden: boolean;
  onPick: (v: T) => void;
  onDefault: () => void;
  note: string | null;
}) {
  const { t } = useT();
  const group = useRef<HTMLDivElement>(null);
  const checked = Math.max(0, options.indexOf(value));

  /** Arrow keys move and select, Home/End jump: the ARIA radio-group keyboard pattern. */
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"];
    if (!keys.includes(e.key)) return;
    e.preventDefault();
    let nextIndex = checked;
    if (e.key === "Home") nextIndex = 0;
    else if (e.key === "End") nextIndex = options.length - 1;
    else nextIndex = (checked + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    onPick(options[nextIndex]);
    requestAnimationFrame(() => group.current?.querySelectorAll<HTMLElement>('[role="radio"]')[nextIndex]?.focus());
  }

  return (
    <div className="grid gap-3 border-t border-rule py-4 first:border-t-0 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] md:gap-6">
      <div className="flex flex-col gap-2">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink-950">
          {label}
          {overridden && <span className="rounded-full bg-saffron-100 px-2 py-0.5 text-xs font-medium text-saffron-ink">{t("toggles.override")}</span>}
        </span>
        <div ref={group} role="radiogroup" aria-label={label} onKeyDown={onKeyDown} className="inline-flex self-start rounded-lg border border-rule bg-paper-sunk p-0.5">
          {options.map((o) => (
            <button
              key={o}
              type="button"
              role="radio"
              aria-checked={value === o}
              tabIndex={value === o ? 0 : -1}
              onClick={() => value !== o && onPick(o)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                value === o ? "bg-paper-raised font-semibold text-ink-950 shadow-[0_1px_2px_rgb(13_13_12/0.08)]" : "font-medium text-ink-500 hover:text-ink-950"
              }`}
            >
              {t(optionKey(o))}
            </button>
          ))}
        </div>
        {overridden && (
          <button type="button" className="link self-start text-xs" onClick={onDefault}>
            {t("toggles.use_default")}
          </button>
        )}
      </div>
      {note && (
        <p className="rounded-lg bg-paper px-3 py-2.5 text-xs leading-relaxed text-ink-700">
          <span className="font-medium text-ink-950">{t("toggles.engine_says")} </span>
          {note}
        </p>
      )}
    </div>
  );
}

/**
 * Rate mode and appropriation, sent as config_overrides so the engine
 * re-evaluates (8.1). The selected value is what the engine reports it used.
 */
export function PricingToggles({
  request,
  response,
  onChange,
}: {
  request: CaseRequest;
  response: CaseResponse;
  onChange: (next: CaseRequest) => void;
}) {
  const { t } = useT();
  const fin = response.financials;
  if (!fin) return null;
  const overrides = request.config_overrides ?? {};

  const setOverride = (patch: Partial<NonNullable<CaseRequest["config_overrides"]>>) => {
    const merged = { ...overrides, ...patch };
    const cleaned = Object.fromEntries(Object.entries(merged).filter(([, v]) => v !== null && v !== undefined));
    onChange({ ...request, config_overrides: Object.keys(cleaned).length ? cleaned : null });
  };

  return (
    <section aria-labelledby="toggles-title" className="panel flex flex-col gap-4 p-6">
      <div className="flex flex-col gap-1">
        <h2 id="toggles-title" className="section-title">{t("toggles.title")}</h2>
        <p className="text-sm text-ink-600">{t("toggles.intro")}</p>
      </div>
      <div className="flex flex-col">
        <Toggle
          label={t("toggles.rate_mode")}
          options={MODES}
          value={fin.rate_mode}
          optionKey={(v) => `toggles.mode.${v}` as const}
          overridden={Boolean(overrides.rate_mode)}
          onPick={(v) => setOverride({ rate_mode: v })}
          onDefault={() => setOverride({ rate_mode: null })}
          note={engineSays(response, "Rate mode ")}
        />
        <Toggle
          label={t("toggles.appropriation")}
          options={APPS}
          value={fin.appropriation_mode}
          optionKey={(v) => `toggles.app.${v}` as const}
          overridden={Boolean(overrides.appropriation_mode)}
          onPick={(v) => setOverride({ appropriation_mode: v })}
          onDefault={() => setOverride({ appropriation_mode: null })}
          note={engineSays(response, "Appropriation mode ")}
        />
      </div>
    </section>
  );
}
