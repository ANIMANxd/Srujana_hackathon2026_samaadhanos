"use client";

import { useEffect, useState } from "react";
import { paiseToMoney, toPaise, money } from "@/lib/format";
import { useT } from "@/lib/i18n";

/**
 * The only arithmetic in the frontend, as architecture §10 allows:
 * interest_outstanding + daily_accrual x elapsed time since page load.
 * Exact integer paise (BigInt), no floats.
 */
export function LiveInterestTicker({
  interest,
  dailyAccrual,
  className = "",
}: {
  interest: string;
  dailyAccrual: string;
  className?: string;
}) {
  const { t } = useT();
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => setElapsedMs(Date.now() - start), 1000);
    return () => clearInterval(id);
  }, [interest, dailyAccrual]);

  const base = toPaise(interest);
  const daily = toPaise(dailyAccrual);
  if (base === null || daily === null) return <span className={`num ${className}`}>{money(interest)}</span>;

  const accrued = (daily * BigInt(elapsedMs)) / BigInt(86_400_000);
  const shown = paiseToMoney(base + accrued);

  return (
    <span className={`num ${className}`} aria-live="off" title={t("money.ticker_label")}>
      <span key={shown} className="animate-tick">
        {shown}
      </span>
    </span>
  );
}
