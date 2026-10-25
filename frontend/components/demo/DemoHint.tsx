"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { DEMO_STEPS, DEMO_TOTAL, demoStepIndex } from "@/lib/demo";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState } from "@/lib/params";
import { Icon } from "../common/Icon";

/**
 * The scripted hint strip for ?demo=1. It sits inside the sticky top bar (so it
 * never covers page content and never shifts it), and its only action is a link
 * to the next screen. No request, engine call or number lives here.
 */
export function DemoHint() {
  const { t } = useT();
  const { demo, view } = useUrlState();
  const href = useHref();
  const pathname = usePathname();
  const [hidden, setHidden] = useState(false);

  if (!demo) return null;

  if (hidden) {
    return (
      <div className="no-print border-t border-rule bg-paper/80">
        <div className="mx-auto flex h-8 max-w-[1200px] items-center px-4 sm:px-8">
          <button
            type="button"
            onClick={() => setHidden(false)}
            className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs font-medium text-ink-500 hover:bg-paper-sunk hover:text-ink-950"
            aria-label={t("demo.show")}
          >
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-saffron-500" />
            {t("demo.label")} · {t("demo.show")}
          </button>
        </div>
      </div>
    );
  }

  const index = demoStepIndex(pathname, view);
  const current = index >= 0 ? DEMO_STEPS[index] : null;
  const atEnd = index === DEMO_TOTAL - 1;
  const next = index < 0 || atEnd ? DEMO_STEPS[0] : (DEMO_STEPS[index + 1] ?? null);
  const nextHref = next ? href(next.paths[0], { view: next.view ?? "supplier" }) : null;
  const nextLabel = !next
    ? ""
    : index < 0
      ? t("demo.start")
      : atEnd
        ? t("demo.restart")
        : t("demo.next", { title: t(next.titleKey) });

  return (
    <div data-demo-hint className="no-print border-t border-rule bg-paper/80">
      <div
        role="region"
        aria-label={t("demo.script")}
        className="mx-auto flex min-h-9 max-w-[1200px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1.5 text-xs sm:px-8"
      >
        <span className="inline-flex shrink-0 items-center gap-1.5 font-medium text-saffron-ink">
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-saffron-500" />
          {t("demo.label")}
          {current && <span className="num text-ink-500">· {t("demo.step", { n: current.n })}</span>}
        </span>

        {current ? (
          <span className="hidden min-w-0 items-center gap-2 sm:inline-flex">
            <span className="font-medium text-ink-950">{t(current.titleKey)}</span>
            <span aria-hidden="true" className="text-ink-500">·</span>
            <span className="truncate text-ink-600">{t(current.hintKey)}</span>
          </span>
        ) : (
          <span className="hidden text-ink-600 md:inline">{t("demo.start_hint")}</span>
        )}

        <span className="ml-auto inline-flex items-center gap-2">
          {nextHref && next && (
            <Link
              href={nextHref}
              scroll={false}
              data-demo-next
              className="inline-flex shrink-0 items-center gap-1 rounded-full bg-ink-950 px-2.5 py-1 font-medium text-paper-raised hover:bg-ink-800"
            >
              {nextLabel}
              <Icon name="arrow-right" className="h-3 w-3" />
            </Link>
          )}
          <button
            type="button"
            onClick={() => setHidden(true)}
            className="grid h-5 w-5 shrink-0 place-items-center rounded-full text-ink-500 hover:bg-paper-sunk hover:text-ink-950"
            aria-label={t("demo.hide")}
          >
            <Icon name="close" className="h-3 w-3" />
          </button>
        </span>
      </div>
    </div>
  );
}
