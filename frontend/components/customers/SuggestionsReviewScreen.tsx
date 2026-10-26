"use client";

// The same review as the Dues drawer, on its own page so the link still
// resolves. Attach, link as group and "not the same" all answer with an Undo toast.

import Link from "next/link";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { Icon } from "../common/Icon";
import { SuggestionsPanel } from "./SuggestionsPanel";
import { UndoToast, useUndoToast } from "./UndoToast";

export function SuggestionsReviewScreen() {
  const { t } = useT();
  const href = useHref();
  const toast = useUndoToast();

  return (
    <div className="flex flex-col gap-6">
      <Link href={href("/")} className="inline-flex items-center gap-1.5 self-start text-sm text-ink-600 hover:text-ink-950">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("review.back")}
      </Link>
      <header className="flex flex-col gap-1">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-ink-950">{t("review.title")}</h1>
        <p className="text-sm text-ink-500">{t("review.subtitle")}</p>
      </header>
      <SuggestionsPanel toast={toast} />
      {toast.shown && (
        <div className="sticky bottom-4">
          <UndoToast toast={toast} />
        </div>
      )}
    </div>
  );
}
