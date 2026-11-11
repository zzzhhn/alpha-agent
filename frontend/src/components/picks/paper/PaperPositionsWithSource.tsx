"use client";

import clsx from "clsx";
import type { PositionOut, TickerAttribution } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmButton } from "@/components/tm/TmButton";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";
import { botZonedTime } from "./PaperBotUi";

function sourceLabel(source: TickerAttribution["source_type"] | undefined, locale: "zh" | "en") {
  if (source === "pick") return t(locale, "sim.workspace.source_pick");
  if (source === "mixed") return t(locale, "sim.workspace.source_mixed");
  if (source === "manual") return t(locale, "sim.workspace.source_manual");
  return locale === "zh" ? "来源待确认" : "Source unavailable";
}

export default function PaperPositionsWithSource({
  positions,
  attribution,
  attributionAvailable = true,
  pendingOrders = 0,
  onChoose,
  chooseDisabledReason,
  accountKind = "human",
  onReview,
}: {
  readonly positions: readonly PositionOut[];
  readonly attribution: readonly TickerAttribution[];
  readonly attributionAvailable?: boolean;
  readonly pendingOrders?: number;
  readonly onChoose?: () => void;
  /** Shown instead of the CTA when ordering is paused, so the empty state is not a dead end. */
  readonly chooseDisabledReason?: string;
  readonly accountKind?: "human" | "bot";
  readonly onReview?: (ticker: string) => void;
}) {
  const { locale } = useLocale();
  const { timeZone } = useTimezonePreference();
  const sourceByTicker = new Map((attributionAvailable ? attribution : []).map((row) => [row.ticker, row]));

  if (positions.length === 0) {
    if (accountKind === "bot") return <TmStatePane state="empty" title={t(locale, "sim.bot.positions_empty")} description={pendingOrders > 0 ? `${pendingOrders} ${t(locale, "sim.status.pending")}` : undefined} className="!min-h-[180px] rounded-none border-0 !bg-transparent" />;
    return <TmStatePane state="empty" title={locale === "zh" ? "尚未建立持仓" : "No positions yet"} description={pendingOrders > 0 ? (locale === "zh" ? `${pendingOrders} 笔订单待成交；下单成功不等于已经持有。` : `${pendingOrders} orders await execution. Submission is not a fill.`) : chooseDisabledReason ?? (locale === "zh" ? "从上方选择推荐并提交模拟单，成交后将在这里显示持仓与来源。" : "Select a recommendation above. Positions and provenance appear after the order fills.")} action={onChoose ? {label:locale === "zh" ? "查看下单区" : "View order ticket",onClick:onChoose,variant:"secondary"} : undefined} className="!min-h-[180px] rounded-none border-0 !bg-transparent" />;
  }

  const headers = [
    t(locale, "sim.attribution.col_ticker"),
    t(locale, "sim.workspace.qty"),
    t(locale, "sim.workspace.avg_cost"),
    t(locale, accountKind === "bot" ? "sim.bot.snapshot_value" : "sim.workspace.current_value"),
    t(locale, accountKind === "bot" ? "sim.bot.snapshot_pnl" : "sim.workspace.pnl"),
    t(locale, accountKind === "bot" && onReview ? "sim.bot.holding_review" : "sim.workspace.source"),
  ];

  return (
    <TmTableFrame>
      <TmTable density="standard" caption={t(locale, "sim.positions.title")} className="text-left">
        <TmTableHead>
          <TmTableRow>
            {headers.map((header, index) => (
              <TmTableHeaderCell key={header} textAlign={index > 0 && index < 5 ? "right" : "left"}>
                {header}
              </TmTableHeaderCell>
            ))}
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {positions.map((position) => {
            const source = sourceByTicker.get(position.ticker);
            const pnlPositive = position.unrealized_pnl !== null && position.unrealized_pnl >= 0;
            const pnlKnown = position.unrealized_pnl !== null && position.unrealized_pct !== null && (position.current_price !== null || accountKind !== "bot");
            const currentValue = position.current_price === null
              ? null
              : position.current_price * position.qty;
            const markTime = position.mark_at ? new Date(position.mark_at) : null;
            const markLabel = position.price_quality === "stale" ? "sim.bot.quote_stale"
              : position.price_quality === "session_close" ? "sim.bot.quote_close"
              : position.price_quality === "fresh" ? "sim.bot.quote_intraday" : "sim.bot.quote_unverified";
            return (
              <TmTableRow key={position.ticker}>
                <TmTableRowHeader className="text-[12px] font-semibold text-tm-accent">{position.ticker}</TmTableRowHeader>
                <TmTableCell numeric textAlign="right" className="text-xs text-tm-fg-2">{position.qty.toLocaleString()}</TmTableCell>
                <TmTableCell numeric textAlign="right" className="text-xs text-tm-fg-2">${position.avg_cost.toFixed(2)}</TmTableCell>
                <TmTableCell numeric textAlign="right" className="text-xs text-tm-fg-2">
                  {currentValue === null ? "—" : `$${currentValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
                  {accountKind === "bot" && currentValue !== null ? <span className={clsx("mt-1 block font-normal", position.price_quality === "stale" ? "text-tm-warn" : "text-tm-muted")}>
                    {t(locale, markLabel)}{markTime && Number.isFinite(markTime.getTime()) ? <> · <time dateTime={position.mark_at!}>{botZonedTime(position.mark_at, locale, timeZone)}</time></> : null}
                  </span> : null}
                </TmTableCell>
                <TmTableCell numeric textAlign="right" className={clsx("text-xs font-semibold", !pnlKnown ? "text-tm-muted" : pnlPositive ? "text-tm-pos" : "text-tm-neg")}>
                  {!pnlKnown || position.unrealized_pnl === null || position.unrealized_pct === null ? "—" : <>{pnlPositive ? "+" : "-"}${Math.abs(position.unrealized_pnl).toLocaleString(undefined, { maximumFractionDigits: 0 })}<span className="ml-1 font-normal">({position.unrealized_pct >= 0 ? "+" : ""}{position.unrealized_pct.toFixed(2)}%)</span></>}
                </TmTableCell>
                <TmTableCell>
                  {accountKind === "bot" && onReview ? <TmButton variant="ghost" size="xs" aria-label={`${t(locale,"sim.bot.holding_review")} ${position.ticker}`} onClick={()=>onReview(position.ticker)}>{t(locale,"sim.bot.holding_review")}</TmButton> : <span className={clsx(
                    "border px-1.5 py-0.5 font-tm-mono text-xs uppercase tracking-wide",
                    source?.source_type === "pick" ? "border-tm-accent text-tm-accent" : "border-tm-rule text-tm-fg-2",
                  )}>{accountKind === "bot" ? t(locale, "sim.bot.position_source") : sourceLabel(source?.source_type, locale)}</span>}
                  {source?.latest_pick_date ? <span className="ml-2 font-tm-mono text-xs text-tm-muted">{source.latest_pick_date}</span> : null}
                </TmTableCell>
              </TmTableRow>
            );
          })}
        </TmTableBody>
      </TmTable>
      <p className="px-3 py-2 font-tm-mono text-xs leading-4 text-tm-muted">
        {t(locale, accountKind === "bot" ? "sim.bot.account_source" : "sim.workspace.source_note")}
      </p>
    </TmTableFrame>
  );
}
