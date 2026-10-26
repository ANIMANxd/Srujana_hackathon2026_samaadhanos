"use client";

// The entry point to the duplicates review from the Dues view: a banner that
// opens the review in a drawer. The Undo toast lives inside the drawer while it
// is open (so Tab can reach it) and on the page once it closes.

import { useMemo, useState } from "react";
import { listSuggestions } from "@/lib/api";
import { useBookRead } from "@/lib/customerBook";
import { count } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { Drawer } from "../common/Drawer";
import { Icon } from "../common/Icon";
import { SuggestionsPanel } from "./SuggestionsPanel";
import { UndoToast, useUndoToast } from "./UndoToast";

export function SuggestionsDrawer() {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const read = useBookRead("suggestions", true, listSuggestions, "customers.load_failed");
  const people = useMemo(() => new Set((read.data ?? []).flatMap((s) => [s.a, s.b])).size, [read.data]);
  const toast = useUndoToast(read.refresh);
  const hasPairs = (read.data?.length ?? 0) > 0;

  return (
    <>
      {(hasPairs || toast.shown) && (
        <div className="flex flex-col gap-2">
          {hasPairs && (
            <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-info/25 bg-info-wash px-3.5 py-2 text-sm text-info">
              <Icon name="info" className="h-4 w-4" />
              <p className="font-medium">{t("customers.suggestions", { n: count(people) })}</p>
              <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" className="inline-flex items-center gap-1 font-medium underline underline-offset-2">
                {t("customers.suggestions_review")}
                <Icon name="arrow-right" className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          {!open && <UndoToast toast={toast} />}
        </div>
      )}
      <Drawer open={open} onClose={() => setOpen(false)} title={t("review.title")} width="lg">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-500">{t("review.subtitle")}</p>
          <SuggestionsPanel toast={toast} />
        </div>
        {open && toast.shown && (
          <div className="sticky bottom-0 -mx-6 -mb-6 mt-4 px-6 pb-6">
            <UndoToast toast={toast} />
          </div>
        )}
      </Drawer>
    </>
  );
}
