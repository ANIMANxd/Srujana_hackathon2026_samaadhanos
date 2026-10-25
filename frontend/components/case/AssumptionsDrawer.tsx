"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { isConfigEntry, type CaseResponse, type StatuteConfig } from "@/lib/types";
import type { Tone } from "@/lib/derive";
import { Drawer } from "../common/Drawer";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";

const SEVERITY_TONE: Record<string, Tone> = { INFO: "info", WARN: "warn", BLOCK: "block" };

function valueText(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

/** Assumptions, warnings, citations and statute constants, with verified flags shown, not hidden. */
export function AssumptionsDrawer({
  response,
  config,
  configLoading,
  configIsStub,
}: {
  response: CaseResponse;
  config: StatuteConfig | null;
  configLoading: boolean;
  configIsStub: boolean;
}) {
  const { t, tWarning } = useT();
  const [open, setOpen] = useState(false);
  const configRows = config
    ? Object.entries(config).filter(([k, v]) => !k.startsWith("_") && isConfigEntry(v))
    : [];

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="panel flex w-full items-center justify-between gap-3 px-6 py-4 text-left transition-colors hover:bg-paper"
      >
        <span className="flex items-center gap-2.5 text-sm font-medium text-ink-950">
          <Icon name="doc" className="h-4 w-4 text-ink-500" />
          {t("assumptions.title")}
        </span>
        <span className="flex items-center gap-2 text-xs text-ink-500">
          {t("assumptions.summary", { w: response.warnings.length, a: response.assumptions.length })}
          <Icon name="chevron" className="h-4 w-4" />
        </span>
      </button>

      <Drawer open={open} onClose={() => setOpen(false)} title={t("assumptions.title")} width="lg">
        <div className="flex flex-col gap-7">
          <p className="text-sm text-ink-600">{t("assumptions.intro")}</p>

          <section>
            <h3 className="section-title border-b border-rule pb-2">{t("assumptions.section.warnings")}</h3>
            {response.warnings.length === 0 ? (
              <p className="mt-2 text-sm text-ink-600">{t("assumptions.none")}</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-3">
                {response.warnings.map((w, i) => (
                  <li key={`${w.code}-${i}`} className="flex flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <StatusIcon size="sm" tone={SEVERITY_TONE[w.severity] ?? "info"} label={t(`severity.${w.severity}`)} />
                      <code className="text-xs text-ink-600">{w.code}</code>
                    </span>
                    <span className="text-sm text-ink-800">{tWarning(w.code, w.text)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="section-title border-b border-rule pb-2">{t("assumptions.section.assumptions")}</h3>
            {response.assumptions.length === 0 ? (
              <p className="mt-2 text-sm text-ink-600">{t("assumptions.none")}</p>
            ) : (
              <ul className="mt-3 list-disc pl-5 text-sm text-ink-800">
                {response.assumptions.map((a, i) => (
                  <li key={i} className="mb-1">{a}</li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="section-title border-b border-rule pb-2">{t("assumptions.section.citations")}</h3>
            {response.citations.length === 0 ? (
              <p className="mt-2 text-sm text-ink-600">{t("assumptions.none")}</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-2 text-sm">
                {response.citations.map((c) => (
                  <li key={c.id} className="flex flex-col gap-1 border-b border-rule pb-2">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink-900">{c.rule}</span>
                      <StatusIcon size="sm" tone={c.verified ? "ok" : "warn"} label={t(c.verified ? "badge.verified" : "badge.unverified")} />
                    </span>
                    <span className="text-xs text-ink-600">
                      {c.statute_ref}
                      {c.config_key ? ` · ${c.config_key}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="section-title border-b border-rule pb-2">{t("assumptions.section.config")}</h3>
            {configLoading ? (
              <p className="mt-2 text-sm text-ink-600">{t("state.loading")}</p>
            ) : !config ? (
              <p className="mt-2 text-sm text-ink-600">{t("assumptions.config_unavailable")}</p>
            ) : configIsStub ? (
              <p className="mt-2 text-sm text-warn">{t("assumptions.config_stub")}</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-2 text-sm">
                {configRows.map(([key, v]) => {
                  if (!isConfigEntry(v)) return null;
                  return (
                    <li key={key} className="flex flex-col gap-1 border-b border-rule pb-2">
                      <span className="flex flex-wrap items-center gap-2">
                        <code className="font-semibold text-ink-900">{key}</code>
                        <StatusIcon size="sm" tone={v.verified ? "ok" : "warn"} label={t(v.verified ? "badge.verified" : "badge.unverified")} />
                      </span>
                      <code className="num break-all text-xs text-ink-800">{valueText(v.value)}</code>
                      <span className="text-xs text-ink-600">{v.source_ref}{v.note ? ` · ${v.note}` : ""}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </Drawer>
    </>
  );
}
