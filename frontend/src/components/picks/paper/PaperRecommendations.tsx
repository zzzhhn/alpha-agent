"use client";

import clsx from "clsx";
import type { RatingCard } from "@/lib/api/picks";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
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
          const confidence = pick.confidence;
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
                <div className="truncate text-[12px] text-tm-fg">{company ?? pick.ticker}</div>
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
                title={t(locale, "sim.workspace.confidence_5d")}
                aria-label={t(locale, "sim.workspace.confidence_5d")}
              >
                {typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "—"}
              </div>
              <div className="min-w-0 truncate text-xs text-tm-muted">{rationale || "—"}</div>
              <TmButton variant="secondary" className="px-2 py-1" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                {t(locale, "sim.workspace.follow")}
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
            {[t(locale, "sim.workspace.company_ticker"), t(locale, "sim.form.side_label"), t(locale, "sim.workspace.latest_close"), t(locale, "sim.workspace.day_change"), t(locale, "sim.workspace.confidence_5d"), t(locale, "sim.workspace.rationale"), ""].map((label) => (
              <TmTableHeaderCell key={label || "action"}>{label}</TmTableHeaderCell>
            ))}
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {picks.map((pick) => {
            const selected = selectedTicker === pick.ticker;
            const company = locale === "zh"
              ? pick.company_name_zh ?? pick.company_name
              : pick.company_name;
            const confidence = pick.confidence;
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
                <TmTableRowHeader className="font-normal">
                  <div className="text-[12px] text-tm-fg">{company ?? pick.ticker}</div>
                  <div className="font-tm-mono text-xs font-semibold text-tm-accent">{pick.ticker}</div>
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
                <TmTableCell numeric className="text-xs text-tm-fg-2">
                  {typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "—"}
                </TmTableCell>
                <TmTableCell className="max-w-48 text-xs leading-4 text-tm-muted">{rationale || "—"}</TmTableCell>
                <TmTableCell className="text-right">
                  <TmButton variant="secondary" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                    {t(locale, "sim.workspace.follow")}
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
