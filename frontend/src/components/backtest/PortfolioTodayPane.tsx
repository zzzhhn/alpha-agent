"use client";

/**
 * PortfolioTodayPane (T6) — last populated session's long/short basket.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 702-824).
 *
 * Requires `daily_breakdown` on the response (set `include_breakdown=true`
 * on the request). Renders an "unavailable" state when missing.
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

export function PortfolioTodayPane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="PORTFOLIO.TODAY">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }

  const breakdown = currentRun.raw.daily_breakdown;
  if (!breakdown || breakdown.length === 0) {
    return (
      <TmPane title="PORTFOLIO.TODAY">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  if (populated.length === 0) {
    return (
      <TmPane title="PORTFOLIO.TODAY">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const today = populated[populated.length - 1];
  const last5 = populated.slice(-5);
  const long5dContrib = new Map<string, number>();
  const short5dContrib = new Map<string, number>();
  for (const d of last5) {
    for (const e of d.long_basket) {
      long5dContrib.set(
        e.ticker,
        (long5dContrib.get(e.ticker) ?? 0) + e.weight * d.daily_return,
      );
    }
    for (const e of d.short_basket) {
      short5dContrib.set(
        e.ticker,
        (short5dContrib.get(e.ticker) ?? 0) + e.weight * d.daily_return,
      );
    }
  }
  const topLong = today.long_basket
    .slice()
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 10);
  const topShort = today.short_basket
    .slice()
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 10);

  return (
    <TmPane title="PORTFOLIO.TODAY" meta={`as_of ${today.date}`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.holdings.subtitle" as Parameters<typeof t>[1])}
      </p>
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2">
        <BasketSide
          title={t(locale, "backtest.holdings.longTop10" as Parameters<typeof t>[1])}
          tone="pos"
          rows={topLong}
          contribMap={long5dContrib}
        />
        <BasketSide
          title={t(locale, "backtest.holdings.shortTop10" as Parameters<typeof t>[1])}
          tone="neg"
          rows={topShort}
          contribMap={short5dContrib}
        />
      </div>
    </TmPane>
  );
}

function BasketSide({
  title,
  tone,
  rows,
  contribMap,
}: {
  readonly title: string;
  readonly tone: "pos" | "neg";
  readonly rows: readonly { ticker: string; weight: number }[];
  readonly contribMap: ReadonlyMap<string, number>;
}) {
  const accentClass = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className="flex flex-col bg-tm-bg">
      <div
        className={`border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${accentClass}`}
      >
        {title}
      </div>
      <div
        className="grid gap-px bg-tm-rule"
        style={{
          gridTemplateColumns:
            "32px minmax(80px, 100px) minmax(80px, 100px) minmax(100px, 1fr)",
        }}
      >
        <RHeader>#</RHeader>
        <RHeader>ticker</RHeader>
        <RHeader align="right">weight</RHeader>
        <RHeader align="right">5d contrib</RHeader>
        {rows.map((r, i) => {
          const contrib = contribMap.get(r.ticker) ?? 0;
          return (
            <BasketRow
              key={r.ticker}
              rank={i + 1}
              ticker={r.ticker}
              weight={r.weight}
              contrib={contrib}
              accentClass={accentClass}
            />
          );
        })}
      </div>
    </div>
  );
}

function BasketRow({
  rank,
  ticker,
  weight,
  contrib,
  accentClass,
}: {
  readonly rank: number;
  readonly ticker: string;
  readonly weight: number;
  readonly contrib: number;
  readonly accentClass: string;
}) {
  return (
    <>
      <RCell>
        <span className="text-tm-muted">{String(rank).padStart(2, "0")}</span>
      </RCell>
      <RCell>
        <span className={`font-semibold ${accentClass}`}>{ticker}</span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">
          {(weight * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${contrib >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {contrib >= 0 ? "+" : ""}
          {(contrib * 10000).toFixed(1)} bps
        </span>
      </RCell>
    </>
  );
}

function RHeader({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function RCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
    >
      {children}
    </div>
  );
}

function UnavailableMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[120px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}
