"use client";

import type { RatingCard } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useMemo } from "react";
import PickRow from "./PickRow";
import { GradeStripHeader, computeHiddenDims } from "./GradeStrip";

const TH = "px-3 py-2.5 font-tm-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-tm-muted select-none";

export default function PicksTable({
  picks,
  isWatched,
}: {
  picks: RatingCard[];
  isWatched?: (ticker: string) => boolean;
}) {
  const { locale } = useLocale();
  // Drop dimension columns that are dead across every visible pick.
  const hiddenDims = useMemo(() => computeHiddenDims(picks), [picks]);
  // Freshest as_of in the list, so each row can flag if its own data lags it.
  const freshestAsOf = useMemo(
    () =>
      picks.reduce<string | null>(
        (mx, p) => (p.as_of && (!mx || p.as_of > mx) ? p.as_of : mx),
        null,
      ),
    [picks],
  );

  if (picks.length === 0) {
    return (
      <div className="px-3 py-6 font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "picks_table.empty")}
      </div>
    );
  }

  return (
    <table className="w-full border-collapse">
      <thead className="border-b border-tm-rule bg-tm-bg-2">
        <tr>
          <th className={`${TH} text-left w-8`}>{t(locale, "picks_table.col_rank")}</th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_ticker")}</th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_rating")}</th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_suggestion")}</th>
          <th className={`${TH} text-right`}>{t(locale, "picks_table.col_composite")}</th>
          <th className={`${TH} text-right`}>{t(locale, "picks_table.col_confidence")}</th>
          <th className={`${TH} text-left`}>
            <span className="flex flex-col gap-0.5">
              <span>{t(locale, "picks_table.col_grades")}</span>
              <GradeStripHeader locale={locale} hidden={hiddenDims} />
            </span>
          </th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_drivers_drags")}</th>
        </tr>
      </thead>
      <tbody>
        {picks.map((card, i) => (
          <PickRow
            key={card.ticker}
            rank={i + 1}
            card={card}
            watched={isWatched?.(card.ticker) ?? false}
            locale={locale}
            hiddenDims={hiddenDims}
            freshestAsOf={freshestAsOf}
          />
        ))}
      </tbody>
    </table>
  );
}
