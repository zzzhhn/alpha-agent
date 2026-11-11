"use client";

import clsx from "clsx";
import type { RatingCard } from "@/lib/api/picks";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
import { HoverTip } from "@/components/ui/HoverTip";
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

const TIER_TONE: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

function pct(value: number | null | undefined): string {
  if (typeof value !== "number" || !isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function PaperRecommendations({
  picks,
  selectedTicker,
  actionable,
  onSelect,
}: {
  readonly picks: readonly RatingCard[];
  readonly selectedTicker: string | null;
  readonly actionable: boolean;
  readonly onSelect: (pick: RatingCard) => void;
}) {
  const { locale } = useLocale();

  if (picks.length === 0) {
    return (
      <p className="px-3 py-8 font-tm-mono text-xs text-tm-muted">
        {t(locale, "sim.workspace.no_picks")}
      </p>
    );
  }

  return (
    <>
      <div className="divide-y divide-tm-rule sm:hidden">
        {picks.map((pick) => {
          const selected = selectedTicker === pick.ticker;
          const company = locale === "zh"
            ? pick.company_name_zh ?? pick.company_name
            : pick.company_name;
          const rankScore = pick.rank_score;
          const rationale = (pick.top_drivers ?? [])
            .slice(0, 2)
            .map((name) => getSignalDisplayLabel(name, locale))
            .join(" · ");
          return (
            <article
              key={pick.ticker}
              className={clsx(
                "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 px-3 py-3",
                selected && "bg-tm-accent-soft outline outline-1 -outline-offset-1 outline-tm-accent",
              )}
            >
              <div className="min-w-0">
                <div className={clsx("truncate text-[12px]", company ? "text-tm-fg" : "text-tm-muted")}>{company ?? (locale === "zh" ? "名称缺失" : "Name unavailable")}</div>
                <div className="font-tm-mono text-xs font-semibold text-tm-accent">{pick.ticker}</div>
              </div>
              <div className="text-right">
                <div className={clsx("font-tm-mono text-xs font-semibold", TIER_TONE[pick.rating] ?? "text-tm-fg-2")}>{pick.rating}</div>
                <div className={clsx("font-tm-mono text-xs tabular-nums", (pick.daily_change_pct ?? 0) >= 0 ? "text-tm-pos" : "text-tm-neg")}>{pct(pick.daily_change_pct)}</div>
              </div>
              <div className="font-tm-mono text-xs text-tm-fg-2">
                {typeof pick.latest_price === "number" ? `$${pick.latest_price.toFixed(2)}` : "—"}
                <span className="ml-2 text-xs text-tm-muted">{pick.price_date ?? "—"}</span>
              </div>
              <div
                className="font-tm-mono text-xs text-tm-muted"
                title={t(locale, "sim.workspace.rank_score_tip")}
                aria-label={t(locale, "sim.workspace.rank_score")}
              >
                {typeof rankScore === "number" ? rankScore : "—"}
              </div>
              <div className="min-w-0 truncate text-xs text-tm-muted">{rationale || "—"}</div>
              <TmButton variant="secondary" className="px-2 py-1" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                {selected ? (locale === "zh" ? "已选择" : "Selected") : (locale === "zh" ? "选择" : "Select")}
              </TmButton>
            </article>
          );
        })}
      </div>
      <TmTableFrame className="hidden sm:block">
      <TmTable
        density="standard"
        caption={t(locale, "sim.workspace.today_picks")}
        className="min-w-[720px] text-left"
      >
        <TmTableHead>
          <TmTableRow>
            {[t(locale, "sim.workspace.company_ticker"), locale === "zh" ? "评级" : "Rating", t(locale, "sim.workspace.latest_close"), t(locale, "sim.workspace.day_change"), t(locale, "sim.workspace.rank_score"), t(locale, "sim.workspace.rationale"), ""].map((label) => (
              <TmTableHeaderCell key={label || "action"} className={!label ? "sticky right-0 z-10 bg-tm-bg-2" : undefined}>{label || <span className="sr-only">{locale === "zh" ? "操作" : "Action"}</span>}</TmTableHeaderCell>
            ))}
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {picks.map((pick) => {
            const selected = selectedTicker === pick.ticker;
            const company = locale === "zh"
              ? pick.company_name_zh ?? pick.company_name
              : pick.company_name;
            const rankScore = pick.rank_score;
            const rationale = (pick.top_drivers ?? [])
              .slice(0, 2)
              .map((name) => getSignalDisplayLabel(name, locale))
              .join(" · ");
            return (
              <TmTableRow
                key={pick.ticker}
                selected={selected}
                className={selected ? "outline outline-1 -outline-offset-1 outline-tm-accent" : undefined}
              >
                <TmTableRowHeader className="!py-3 font-normal">
                  <div className="font-tm-mono text-sm font-semibold text-tm-accent">{pick.ticker}</div>
                  <HoverTip content={company ?? (locale === "zh" ? "数据源未返回公司名称" : "The data source returned no company name")} className="max-w-48" width={240}><span className="truncate text-xs text-tm-muted">{company ?? (locale === "zh" ? "名称缺失" : "Name unavailable")}</span></HoverTip>
                </TmTableRowHeader>
                <TmTableCell className={clsx("text-xs font-semibold", TIER_TONE[pick.rating] ?? "text-tm-fg-2")}>{pick.rating}</TmTableCell>
                <TmTableCell numeric className="text-xs text-tm-fg-2">
                  {typeof pick.latest_price === "number" ? `$${pick.latest_price.toFixed(2)}` : "—"}
                  {pick.price_date ? <span className="block text-xs text-tm-muted">{pick.price_date}</span> : null}
                </TmTableCell>
                <TmTableCell numeric className={clsx(
                  "text-xs",
                  (pick.daily_change_pct ?? 0) >= 0 ? "text-tm-pos" : "text-tm-neg",
                )}>{pct(pick.daily_change_pct)}</TmTableCell>
                <TmTableCell numeric className="text-xs text-tm-fg-2" title={t(locale, "sim.workspace.rank_score_tip")}>
                  {typeof rankScore === "number" ? rankScore : "—"}
                </TmTableCell>
                <TmTableCell className="max-w-48 text-xs leading-4 text-tm-muted">{rationale || "—"}</TmTableCell>
                <TmTableCell className="sticky right-0 border-l border-tm-rule bg-tm-bg-2 text-right">
                  <TmButton variant="secondary" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                    {selected ? (locale === "zh" ? "已选择" : "Selected") : (locale === "zh" ? "选择" : "Select")}
                  </TmButton>
                </TmTableCell>
              </TmTableRow>
            );
          })}
        </TmTableBody>
      </TmTable>
      </TmTableFrame>
    </>
  );
}
