"use client";

import { useEffect, useState } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import PickRow from "./PickRow";

const TH = "px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted select-none";

export default function PicksTable({
  picks,
  isWatched,
}: {
  picks: RatingCard[];
  isWatched?: (ticker: string) => boolean;
}) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

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
          <th className={`${TH} text-right`}>{t(locale, "picks_table.col_composite")}</th>
          <th className={`${TH} text-right`}>{t(locale, "picks_table.col_confidence")}</th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_top_drivers")}</th>
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
          />
        ))}
      </tbody>
    </table>
  );
}
