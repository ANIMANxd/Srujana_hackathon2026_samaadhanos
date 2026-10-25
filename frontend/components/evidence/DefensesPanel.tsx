"use client";

import { useT } from "@/lib/i18n";
import type { Defense, DefenseStatus } from "@/lib/types";
import { DefenseList } from "../case/DefensesDrawer";
import { Meaning } from "./Meaning";

/** The card speaks to the weakest status present: at risk, then open, then strong. */
function headline(defenses: Defense[]): DefenseStatus | null {
  if (defenses.some((d) => d.status === "AT_RISK")) return "AT_RISK";
  if (defenses.some((d) => d.status === "OPEN_QUESTION")) return "OPEN_QUESTION";
  return defenses.length ? "STRONG" : null;
}

export function DefensesPanel({ defenses }: { defenses: Defense[] }) {
  const { t } = useT();
  const code = headline(defenses);
  return (
    <section aria-labelledby="def-title" className="panel flex flex-col gap-4 p-6">
      <div className="flex flex-col gap-1">
        <h2 id="def-title" className="section-title">{t("defenses.title")}</h2>
        <p className="text-sm text-ink-600">{t("defense.drawer_intro")}</p>
      </div>
      {defenses.length === 0 ? <p className="text-sm text-ink-600">{t("defense.none")}</p> : <DefenseList defenses={defenses} />}
      {code && <Meaning block="defenses" code={code} />}
    </section>
  );
}
