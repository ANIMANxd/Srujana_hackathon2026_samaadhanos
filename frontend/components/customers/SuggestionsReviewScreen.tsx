"use client";

// Possible duplicates, read-only for now: each pair with the server's reason
// and name similarity. Nothing is merged from here; the actions (attach, group,
// "not the same") arrive with the review task (CF4).

import Link from "next/link";
import { useMemo } from "react";
import { listSuggestions } from "@/lib/api";
import { useBookRead } from "@/lib/customerBook";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { useCustomers } from "@/lib/useCustomers";
import { Icon } from "../common/Icon";
import { ErrorState, Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";

export function SuggestionsReviewScreen() {
  const { t } = useT();
  const href = useHref();
  const read = useBookRead("suggestions", true, listSuggestions, "customers.load_failed");
  const book = useCustomers({ sort: "display_name", dir: "asc", grouped: false });
  const names = useMemo(() => new Map((book.rows ?? []).map((r) => [r.id, r.display_name])), [book.rows]);
  const name = (id: string) => names.get(id) ?? id;

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
      {read.source === "offline" && <Banner tone="warn" icon="lock" message="book.offline_sample" />}

      {read.error && !read.data ? (
        <ErrorState message={read.error.detail ?? t(read.error.key)} onRetry={read.refresh} />
      ) : !read.data ? (
        <Skeleton className="h-24" />
      ) : read.data.length === 0 ? (
        <p className="text-sm text-ink-500">{t("review.empty")}</p>
      ) : (
        <ul className="panel divide-y divide-rule">
          {read.data.map((s) => (
            <li key={`${s.a}:${s.b}`} className="flex flex-col gap-2 px-5 py-4">
              <StatusIcon size="sm" tone="info" icon="info" label={t(`review.kind.${s.kind}`)} />
              <p className="font-medium text-ink-950">
                {name(s.a)} <span className="text-ink-500">·</span> {name(s.b)}
              </p>
              <p className="text-sm text-ink-600">{s.reason}</p>
              <p className="num text-xs text-ink-500">{t("review.similarity", { pct: s.similarity })}</p>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-ink-500">{t("review.actions_soon")}</p>
    </div>
  );
}
