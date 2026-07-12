"use client";

import type { RatingCard } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useMemo } from "react";
import { HoverTip } from "@/components/ui/HoverTip";
import PickRow from "./PickRow";
import { GradeStripHeader, computeHiddenDims } from "./GradeStrip";

const TH = "px-3 py-2.5 font-tm-mono text-[12px] font-semibold uppercase tracking-[0.06em] text-tm-fg-2 select-none";

export default function PicksTable({
  picks,
  isWatched,
  simPositions,
  cash,
  onOrderPlaced,
}: {
  picks: RatingCard[];
  isWatched?: (ticker: string) => boolean;
  simPositions?: ReadonlyMap<string, number>;
  cash?: number;
  onOrderPlaced?: () => void;
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
          <th className={`${TH} text-left w-8`}>
            <HoverTip content={t(locale, "picks_table.col_rank_tip")} placement="bottom" width={200}>
              <span className="cursor-help">{t(locale, "picks_table.col_rank")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-left`}>{t(locale, "picks_table.col_ticker")}</th>
          <th className={`${TH} text-left`}>
            <HoverTip content={t(locale, "picks_table.col_rating_tip")} placement="bottom" width={240}>
              <span className="cursor-help">{t(locale, "picks_table.col_rating")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-left`}>
            <HoverTip content={t(locale, "picks_table.col_suggestion_tip")} placement="bottom" width={240}>
              <span className="cursor-help">{t(locale, "picks_table.col_suggestion")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-right`}>
            <HoverTip content={t(locale, "picks_table.col_composite_tip")} placement="bottom" width={260}>
              <span className="cursor-help">{t(locale, "picks_table.col_composite")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-right`}>
            <HoverTip content={t(locale, "picks_table.col_confidence_tip")} placement="bottom" width={280}>
              <span className="cursor-help">{t(locale, "picks_table.col_confidence")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-left`}>
            <HoverTip content={t(locale, "picks_table.col_grades_tip")} placement="bottom" width={260}>
              <span className="flex flex-col gap-0.5 cursor-help">
                <span>{t(locale, "picks_table.col_grades")}</span>
                <GradeStripHeader locale={locale} hidden={hiddenDims} />
              </span>
            </HoverTip>
          </th>
          <th className={`${TH} text-left`}>
            <HoverTip content={t(locale, "picks_table.col_drivers_drags_tip")} placement="bottom" width={260}>
              <span className="cursor-help">{t(locale, "picks_table.col_drivers_drags")}</span>
            </HoverTip>
          </th>
          <th className={`${TH} text-left`}>{t(locale, "sim.tab")}</th>
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
            simPositions={simPositions}
            cash={cash}
            onOrderPlaced={onOrderPlaced}
          />
        ))}
      </tbody>
    </table>
  );
}
