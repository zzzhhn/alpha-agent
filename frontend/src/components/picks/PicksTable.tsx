"use client";

import type { RatingCard } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { TmPagination } from "@/components/tm/TmPagination";
import PicksEvidenceDialog from "./PicksEvidenceDialog";
import styles from "./PicksTable.module.css";

const HEADER_CLASS = "text-[12px] select-none";

export default function PicksTable({
  picks,
  isWatched,
  simPositions,
  cash,
  onOrderPlaced,
  ranked = true,
  ordersDisabled = false,
  pending = false,
}: {
  picks: RatingCard[];
  isWatched?: (ticker: string) => boolean;
  simPositions?: ReadonlyMap<string, number>;
  cash?: number;
  onOrderPlaced?: () => void;
  ranked?: boolean;
  ordersDisabled?: boolean;
  pending?: boolean;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [compact, setCompact] = useState(false);
  const [pageSize, setPageSize] = useState(10);
  const [paging, setPaging] = useState({ source: picks, page: 1 });
  const [evidence, setEvidence] = useState<{ source: RatingCard[]; card: RatingCard } | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  // A new result set starts on page one immediately, including search recovery.
  const pageCount = Math.max(1, Math.ceil(picks.length / pageSize));
  const page = paging.source === picks ? Math.min(paging.page, pageCount) : 1;
  const offset = (page - 1) * pageSize;
  const visiblePicks = picks.slice(offset, offset + pageSize);
  const pageKey = `${page}:${pageSize}:${picks[0]?.ticker}:${picks.at(-1)?.ticker}:${picks.length}:${picks[0]?.as_of}`;
  useLayoutEffect(() => {
    const frame = viewportRef.current?.querySelector<HTMLElement>("[data-picks-scroll]");
    if (frame) frame.scrollTop = 0;
  }, [page, pageSize, picks]);
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

  return (
    <div ref={viewportRef}>
    <div className="border-b border-tm-rule px-3 py-2 text-xs text-tm-muted">
      {zh ? "点击方向一致度数值，查看样本与统计说明" : "Select direction-hit values for sample details and definitions"}
    </div>
    {compact ? <div key={pageKey} className={styles.pageEnter}><PicksCards picks={visiblePicks} rankOffset={offset} ranked={ranked} ordersDisabled={ordersDisabled} onEvidenceOpen={card => setEvidence({ source: picks, card })} /></div> : <TmTableFrame data-picks-scroll role="region" aria-label={zh ? "候选表滚动区" : "Candidate table scroll area"} tabIndex={0} className="max-h-[min(68vh,44rem)] overflow-y-auto overscroll-contain">
    <TmTable density="standard" caption={locale === "zh" ? "今日推荐明细" : "Today's recommendations"} className="min-w-[1060px]">
      <TmTableHead className="sticky top-0 z-10 shadow-[0_1px_0_var(--tm-rule)]">
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
            <HoverTip content={zh ? "次日方向的历史一致度，不是未来胜率。点击行内数值查看样本详情。" : "Historical next-day direction agreement, not future win probability. Select a row's values for sample details."} placement="bottom" width={280}>
              <span className="flex flex-col gap-2 cursor-help">
                <span>{t(locale, "picks_table.col_confidence")}</span>
                <span className="grid grid-cols-4 gap-x-3 text-right font-normal normal-case tracking-normal">
                  {(["picks_table.cons_5d", "picks_table.cons_1m", "picks_table.cons_1y", "picks_table.cons_hist"] as const).map(key => <span key={key} className="min-w-14">{t(locale, key)}</span>)}
                </span>
              </span>
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
      <TmTableBody key={pageKey} className={styles.pageEnter}>
        {visiblePicks.map((card, i) => (
          <PickRow
            key={card.ticker}
            rank={ranked ? offset + i + 1 : null}
            card={card}
            watched={isWatched?.(card.ticker) ?? false}
            locale={locale}
            hiddenDims={hiddenDims}
            freshestAsOf={freshestAsOf}
            simPositions={simPositions}
            cash={cash}
            onOrderPlaced={onOrderPlaced}
            onEvidenceOpen={card => setEvidence({ source: picks, card })}
            ordersDisabled={ordersDisabled}
          />
        ))}
      </TmTableBody>
    </TmTable>
    </TmTableFrame>}
    <TmPagination page={page} pageSize={pageSize} totalItems={picks.length} pageSizeOptions={[10, 25, 50]} loading={pending}
      onPageChange={next => setPaging({ source: picks, page: next })}
      onPageSizeChange={next => { setPageSize(next); setPaging({ source: picks, page: 1 }); }}
      labels={{
        navigation: zh ? "候选分页" : "Candidate pagination",
        previous: zh ? "上一页" : "Previous", previousAriaLabel: zh ? "上一页候选" : "Previous candidates",
        next: zh ? "下一页" : "Next", nextAriaLabel: zh ? "下一页候选" : "Next candidates",
        page: (current, count) => zh ? `第 ${current} / ${count} 页` : `${current} / ${count}`,
        pageSize: zh ? "每页" : "Per page",
        total: total => zh ? `第 ${offset + 1} 至 ${Math.min(offset + pageSize, total)} 条，共 ${total} 条` : `${offset + 1} to ${Math.min(offset + pageSize, total)} of ${total}`,
      }} />
    {evidence?.source === picks ? <PicksEvidenceDialog key={evidence.card.ticker} card={evidence.card} locale={locale} onClose={() => setEvidence(null)} /> : null}
    </div>
  );
}
