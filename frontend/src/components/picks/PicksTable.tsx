"use client";

import type { RatingCard } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useMemo } from "react";
import { useEffect, useState } from "react";
import { HoverTip } from "@/components/ui/HoverTip";
import PickRow from "./PickRow";
import { GradeStripHeader, computeHiddenDims } from "./GradeStrip";
import PicksCards from "./PicksCards";
import {
  TmTable,
  TmTableBody,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
} from "@/components/tm/TmTable";
import { TmStatePane } from "@/components/tm/TmStatePane";

const HEADER_CLASS = "text-[12px] select-none";

export default function PicksTable({
  picks,
  isWatched,
  simPositions,
  cash,
  onOrderPlaced,
  ranked = true,
  ordersDisabled = false,
}: {
  picks: RatingCard[];
  isWatched?: (ticker: string) => boolean;
  simPositions?: ReadonlyMap<string, number>;
  cash?: number;
  onOrderPlaced?: () => void;
  ranked?: boolean;
  ordersDisabled?: boolean;
}) {
  const { locale } = useLocale();
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 767px)");
    const sync = () => setCompact(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
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
      <TmStatePane state="empty" title={t(locale, "picks_table.empty")} className="rounded-none border-0" />
    );
  }

  if (compact) {
    return <PicksCards picks={picks} ranked={ranked} ordersDisabled={ordersDisabled} />;
  }

  return (
    <TmTableFrame>
    <TmTable density="standard" caption={locale === "zh" ? "今日推荐明细" : "Today's recommendations"} className="min-w-[1060px]">
      <TmTableHead>
        <TmTableRow>
          <TmTableHeaderCell className={`${HEADER_CLASS} w-8`}>
            <HoverTip content={t(locale, "picks_table.col_rank_tip")} placement="bottom" width={200}>
              <span className="cursor-help">{t(locale, "picks_table.col_rank")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>{t(locale, "picks_table.col_ticker")}</TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_rating_tip")} placement="bottom" width={240}>
              <span className="cursor-help">{t(locale, "picks_table.col_rating")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_suggestion_tip")} placement="bottom" width={240}>
              <span className="cursor-help">{t(locale, "picks_table.col_suggestion")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell textAlign="right" className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_composite_tip")} placement="bottom" width={260}>
              <span className="cursor-help">{t(locale, "picks_table.col_composite")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell textAlign="right" className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_confidence_tip")} placement="bottom" width={280}>
              <span className="cursor-help">{t(locale, "picks_table.col_confidence")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_grades_tip")} placement="bottom" width={260}>
              <span className="flex flex-col gap-0.5 cursor-help">
                <span>{t(locale, "picks_table.col_grades")}</span>
                <GradeStripHeader locale={locale} hidden={hiddenDims} />
              </span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>
            <HoverTip content={t(locale, "picks_table.col_drivers_drags_tip")} placement="bottom" width={260}>
              <span className="cursor-help">{t(locale, "picks_table.col_drivers_drags")}</span>
            </HoverTip>
          </TmTableHeaderCell>
          <TmTableHeaderCell className={HEADER_CLASS}>{t(locale, "sim.tab")}</TmTableHeaderCell>
        </TmTableRow>
      </TmTableHead>
      <TmTableBody>
        {picks.map((card, i) => (
          <PickRow
            key={card.ticker}
            rank={ranked ? i + 1 : null}
            card={card}
            watched={isWatched?.(card.ticker) ?? false}
            locale={locale}
            hiddenDims={hiddenDims}
            freshestAsOf={freshestAsOf}
            simPositions={simPositions}
            cash={cash}
            onOrderPlaced={onOrderPlaced}
            ordersDisabled={ordersDisabled}
          />
        ))}
      </TmTableBody>
    </TmTable>
    </TmTableFrame>
  );
}
