"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { Icon } from "./Icon";

/** Skeleton block for loading states (no spinners on the hero card). */
export function Skeleton({ className = "h-6 w-full" }: { className?: string }) {
  return <div className={`animate-pulse rounded-sm bg-paper-sunk ${className}`} aria-hidden="true" />;
}

export function CaseSkeleton() {
  const { t } = useT();
  return (
    <div className="flex flex-col gap-5" aria-busy="true">
      <span className="sr-only">{t("state.loading")}</span>
      <Skeleton className="h-8 w-2/3" />
      <div className="panel flex flex-col gap-3 p-6">
        <Skeleton className="h-10 w-4/5" />
        <Skeleton className="h-5 w-3/5" />
        <Skeleton className="h-5 w-2/5" />
        <Skeleton className="h-11 w-48" />
      </div>
      <div className="grid gap-5 md:grid-cols-[3fr_2fr]">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  );
}

export function EmptyState({ title, body, children }: { title: string; body: string; children?: ReactNode }) {
  return (
    <div className="panel flex flex-col items-start gap-3 px-6 py-10">
      <Icon name="ledger" className="h-8 w-8 text-ink-500" />
      <h2 className="font-display text-2xl font-semibold text-ink-950">{title}</h2>
      <p className="max-w-prose text-ink-700">{body}</p>
      {children && <div className="mt-2 flex flex-wrap gap-3">{children}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useT();
  return (
    <div role="alert" className="panel flex flex-col items-start gap-3 border-block/40 px-6 py-8">
      <span className="inline-flex items-center gap-2 font-semibold text-block">
        <Icon name="block" />
        {t("state.error_title")}
      </span>
      <p className="max-w-prose text-ink-700">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          {t("state.retry")}
        </button>
      )}
    </div>
  );
}

export function NotFoundState() {
  const { t } = useT();
  const href = useHref();
  return (
    <EmptyState title={t("state.not_found_title")} body={t("state.not_found_body")}>
      <Link href={href("/")} className="btn btn-secondary">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("nav.back_to_dues")}
      </Link>
    </EmptyState>
  );
}
