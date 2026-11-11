"use client";

import Link from "next/link";
import { useState } from "react";
import type { RatingCard, GradeMethod } from "@/lib/api/picks";
import clsx from "clsx";
import { consistencyEvidence } from "@/lib/picks-evidence";
import WatchlistStar from "@/components/ui/WatchlistStar";
import { HoverTip } from "@/components/ui/HoverTip";
import { TmTooltip } from "@/components/tm/TmTooltip";
import GradeStrip from "./GradeStrip";
import { t, type Locale } from "@/lib/i18n";
// Reuse the app-wide signal→label map (also used by the stock-detail Radar
// and AttributionTable) so the drivers/drags column reads in plain language
// AND stays consistent with how the same signals are labeled elsewhere.
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { getSuggestion } from "@/lib/suggestion";
import SimOrderDrawer from "./SimOrderDrawer";
import { TmButton } from "@/components/tm/TmButton";
import { TmTableCell, TmTableRow, TmTableRowHeader } from "@/components/tm/TmTable";

const TIER_COLOR: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function PickRow({
  rank,
  card, gradeMethod, onResearchOpen,
  watched = false,
  locale = "zh",
  hiddenDims,
  freshestAsOf,
  simPositions,
  cash,
  onOrderPlaced,
  onEvidenceOpen,
  ordersDisabled = false,
}: {
  rank: number | null;
  card: RatingCard;
  gradeMethod?: GradeMethod;
  onResearchOpen?: (card: RatingCard) => void;
  watched?: boolean;
  locale?: Locale;
  hiddenDims?: ReadonlySet<string>;
  // Freshest as_of across the visible list, so a row that lags it (its own
  // data is from an earlier day) is flagged — the list header alone shows the
  // max, which would otherwise hide a stale row behind a fresh-looking time.
  freshestAsOf?: string | null;
  simPositions?: ReadonlyMap<string, number>;  // ticker → qty currently held
  cash?: number;
  onOrderPlaced?: () => void;
  onEvidenceOpen: (card: RatingCard) => void;
  ordersDisabled?: boolean;
}) {
  // Days this row's data lags the freshest row in the list (0 if within ~20h).
  const staleDays = (() => {
    if (!freshestAsOf || !card.as_of) return 0;
    const gap = new Date(freshestAsOf).getTime() - new Date(card.as_of).getTime();
    if (isNaN(gap) || gap <= 0) return 0;
    return gap > 20 * 3_600_000 ? Math.round(gap / 86_400_000) : 0;
  })();
  // Defensive: backend may return null for composite/confidence when legacy
  // DB rows held NaN before storage sanitization landed.
  const composite =
    typeof card.composite_score === "number" && isFinite(card.composite_score)
      ? card.composite_score
      : null;
  const hit =
    typeof card.confidence === "number" && isFinite(card.confidence)
      ? card.confidence
      : 0;
  const rawZ = composite === null ? "—" : `${composite >= 0 ? "+" : ""}${composite.toFixed(3)}σ`;

  // Descriptive 1-day direction agreement: predicted tier vs next-day actual
  // move over trailing windows. null -> "—" (insufficient realized history).
  // Colour only clearly-off-coinflip values (>=55 / <=45 around the structural
  // ~50%); the rest stay neutral so noisy values do not over-claim an edge.
  const CONS_WINDOWS = [
    { key: "d5", labelKey: "picks_table.cons_5d" },
    { key: "m1", labelKey: "picks_table.cons_1m" },
    { key: "y1", labelKey: "picks_table.cons_1y" },
    { key: "hist", labelKey: "picks_table.cons_hist" },
  ] as const;
  // Mirrors backend MIN_SAMPLES (backtest/consistency.py): below this many
  // realized predictions the window shows a dash instead of a rate.
  const consVals = CONS_WINDOWS.map((w) => {
    return {
      label: t(locale, w.labelKey),
      ...consistencyEvidence(card, w.key, locale),
    };
  });

  const drivers = (card.top_drivers ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));
  const drags = (card.top_drags ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));

  const [drawerOpen, setDrawerOpen] = useState(false);
  const heldQty = simPositions?.get(card.ticker) ?? 0;

  return (
    <TmTableRow className="h-11 [&>td]:py-2 [&>th]:py-2">
      <TmTableCell numeric className="text-xs text-tm-muted">
        {rank ?? "—"}
      </TmTableCell>
      <TmTableRowHeader className="text-sm font-semibold">
        {watched ? (
          <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" />
        ) : null}
        <Link
          href={`/stock/${card.ticker}`}
          className="text-tm-accent hover:underline"
        >
          {card.ticker}
        </Link>
        {card.tier_flip_today ? (
          <HoverTip
            content={t(locale, "picks_table.tier_flip_tooltip")}
            placement="bottom"
            className="ml-1 align-middle"
          >
            <span className="cursor-help text-xs font-normal text-tm-warn">
              ⇄
            </span>
          </HoverTip>
        ) : null}
        {card.partial ? (
          <span
            className="ml-1.5 rounded-[2px] bg-tm-bg-2 px-1 py-0.5 align-middle text-xs font-semibold uppercase tracking-wide text-tm-muted"
            title={t(locale, "picks_table.partial_tooltip")}
          >
            {t(locale, "picks_table.partial_badge")}
          </span>
        ) : null}
        {staleDays > 0 ? (
          <span
            className="ml-1.5 rounded-[2px] bg-tm-warn-soft px-1 py-0.5 align-middle text-xs font-semibold tabular-nums text-tm-warn"
            title={
              locale === "zh"
                ? `该行数据比榜单最新时间旧 ${staleDays} 天`
                : `this row's data is ${staleDays}d older than the freshest`
            }
          >
            {staleDays}d
          </span>
        ) : null}
      </TmTableRowHeader>
      <TmTableCell className="text-xs">
        <span
          className={clsx(
            "font-semibold",
            TIER_COLOR[card.rating] ?? "text-tm-fg-2",
          )}
        >
          {card.rating}
        </span>
      </TmTableCell>
      <TmTableCell className="text-sm">
        {(() => {
          const sug = getSuggestion(card.rating, hit, locale);
          const tone =
            sug.tone === "pos"
              ? "text-tm-pos"
              : sug.tone === "neg"
                ? "text-tm-neg"
                : "text-tm-fg-2";
          // Caution: the action stands (the model's tier), but the modest
          // realized edge is disclosed rather than hidden — dimmed + a warn
          // marker that explains the near-coin-flip 5d calibrated confidence on hover.
          return sug.caution ? (
            <HoverTip content={t(locale, "picks_table.sug_caution_tip")} placement="bottom">
              <span className={clsx("font-semibold", tone)}>{sug.label}</span>
              <span className="ml-0.5 cursor-help text-tm-warn">⚠</span>
            </HoverTip>
          ) : (
            <span className={clsx("font-semibold", tone)}>{sug.label}</span>
          );
        })()}
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className="text-sm">
        <TmTooltip content={`${locale === "zh" ? "原始综合分" : "Raw composite"}: ${rawZ} · ${locale === "zh" ? "快照" : "Run"} #${card.run_id ?? "—"}`}><span>{card.rank_score ?? "—"}</span></TmTooltip>
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className="text-xs">
        <TmButton
          variant="ghost"
          className="!h-auto !p-0 !font-normal !tracking-normal hover:bg-tm-bg-3"
          aria-label={`${card.ticker}：${locale === "zh" ? "查看历史方向证据" : "View historical direction evidence"}`}
          aria-haspopup="dialog"
          onClick={() => onEvidenceOpen(card)}
        >
          <span className="grid grid-cols-4 gap-x-3 text-right">
            {consVals.map((c) => (
              <span
                key={c.label + "_v"}
                className={clsx(
                  "min-w-14 tabular-nums",
                  c.pct === null
                    ? "text-tm-muted"
                    : c.pct >= 55
                      ? "text-tm-pos"
                      : c.pct <= 45
                        ? "text-tm-neg"
                        : "text-tm-fg-2",
                )}
              >
                <span className="sr-only">{c.label}：</span>
                <span className="block text-sm underline decoration-dotted underline-offset-4">{c.pct === null ? "—" : `${c.pct}%`}</span>
                <span className="block whitespace-nowrap text-xs text-tm-muted">{c.sampleLabel}</span>
              </span>
            ))}
          </span>
        </TmButton>
      </TmTableCell>
      <TmTableCell>
        <GradeStrip grades={card.dimension_grades ?? {}} scores={card.dimension_scores} method={gradeMethod} locale={locale} hidden={hiddenDims} />
      </TmTableCell>
      <TmTableCell className="font-tm-sans text-[12px]">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {drivers.length > 0 ? (
            <span className="text-tm-pos">
              ↑ {drivers.join(" ")}
            </span>
          ) : null}
          {drags.length > 0 ? (
            <span className="text-tm-neg">
              ↓ {drags.join(" ")}
            </span>
          ) : null}
          {drivers.length === 0 && drags.length === 0 ? (
            <span className="text-tm-muted">—</span>
          ) : null}
        </span>
      </TmTableCell>
      <TmTableCell className="px-2">
        {onResearchOpen ? <TmButton variant="ghost" size="xs" aria-haspopup="dialog" aria-label={`${card.ticker} ${locale === "zh" ? "研究记录" : "research records"}`} onClick={() => onResearchOpen(card)}>{locale === "zh" ? "记录" : "Record"}</TmButton> : null}
        <TmButton
          type="button"
          variant="secondary"
          size="xs"
          onClick={() => setDrawerOpen(true)}
          disabled={ordersDisabled}
          title={ordersDisabled ? t(locale, "picks.stale_order_disabled") : undefined}
          className={clsx(
            "px-1.5 text-xs",
            ordersDisabled
              ? "text-tm-muted"
              : heldQty > 0
              ? "border-tm-pos text-tm-pos hover:border-tm-accent hover:text-tm-accent"
              : "text-tm-muted hover:border-tm-accent hover:text-tm-accent",
          )}
        >
          {heldQty > 0
            ? t(locale, "sim.held_btn")
            : t(locale, "sim.order_btn")}
        </TmButton>
        {drawerOpen && !ordersDisabled && (
          <SimOrderDrawer
            ticker={card.ticker}
            card={card}
            cash={cash}
            onClose={() => setDrawerOpen(false)}
            onOrderPlaced={() => {
              setDrawerOpen(false);
              onOrderPlaced?.();
            }}
          />
        )}
      </TmTableCell>
    </TmTableRow>
  );
}
