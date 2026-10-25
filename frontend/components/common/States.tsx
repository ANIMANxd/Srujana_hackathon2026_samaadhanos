"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { Icon } from "./Icon";

/** Skeleton block for loading states (no spinners on the hero card). */
export function Skeleton({ className = "h-6 w-full" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-paper-sunk ${className}`} aria-hidden="true" />;
}

export function CaseSkeleton() {
  const { t } = useT();
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <span className="sr-only">{t("state.loading")}</span>
      <div className="panel grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col gap-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-11 w-64" />
          <Skeleton className="h-4 w-80 max-w-full" />
        </div>
        <div className="flex flex-col gap-3">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-10 w-40" />
        </div>
      </div>
      <Skeleton className="h-28" />
      <div className="grid gap-4 md:grid-cols-[3fr_2fr]">
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
      </div>
    </div>
  );
}

export function EmptyState({ title, body, children }: { title: string; body: string; children?: ReactNode }) {
  return (
    <div className="panel flex flex-col items-start gap-3 px-6 py-12 sm:px-10">
      <span className="grid h-10 w-10 place-items-center rounded-lg border border-rule bg-paper text-ink-500">
        <Icon name="ledger" className="h-5 w-5" />
      </span>
      <h2 className="mt-2 text-xl font-semibold tracking-[-0.01em] text-ink-950">{title}</h2>
      <p className="max-w-prose text-ink-600">{body}</p>
      {children && <div className="mt-3 flex flex-wrap gap-3">{children}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useT();
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-block/25 bg-block-wash px-4 py-3 text-sm">
      <span className="inline-flex items-center gap-2 font-medium text-block">
        <Icon name="block" className="h-4 w-4" />
        {t("state.error_title")}
      </span>
      <p className="flex-1 text-ink-800">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary min-h-8 px-3" onClick={onRetry}>
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
