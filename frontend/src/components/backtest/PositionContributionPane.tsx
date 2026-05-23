"use client";

/**
 * PositionContributionPane (T6) — top contributors / detractors over the
 * test slice. Chart logic lifted from (dashboard)/backtest/page.tsx
 * (lines 932-1089).
 *
 * Requires `daily_breakdown` on the response.
 */

import { useMemo } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { FactorBacktestResponse } from "@/lib/types";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

interface PositionContrib {
  readonly ticker: string;
  readonly contrib: number;
  readonly nDays: number;
  readonly hitDays: number;
  readonly side: "long" | "short" | "both";
}

function aggregateContribution(
  breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>,
  trainEndIndex: number | null | undefined,
): PositionContrib[] {
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  let testSlice = populated;
  if (
    typeof trainEndIndex === "number" &&
    trainEndIndex > 0 &&
    populated.length > trainEndIndex
  ) {
    testSlice = populated.slice(trainEndIndex);
  }
  const map = new Map<
    string,
    {
      contrib: number;
      nDays: number;
      hitDays: number;
      longDays: number;
      shortDays: number;
    }
  >();
  for (const d of testSlice) {
    for (const e of d.long_basket) {
      const c = e.weight * d.daily_return;
      const cur = map.get(e.ticker) ?? {
        contrib: 0,
        nDays: 0,
        hitDays: 0,
        longDays: 0,
        shortDays: 0,
      };
      cur.contrib += c;
      cur.nDays += 1;
      cur.longDays += 1;
      if (c > 0) cur.hitDays += 1;
      map.set(e.ticker, cur);
    }
    for (const e of d.short_basket) {
      const c = e.weight * d.daily_return;
      const cur = map.get(e.ticker) ?? {
        contrib: 0,
        nDays: 0,
        hitDays: 0,
        longDays: 0,
        shortDays: 0,
      };
      cur.contrib += c;
      cur.nDays += 1;
      cur.shortDays += 1;
      if (c > 0) cur.hitDays += 1;
      map.set(e.ticker, cur);
    }
  }
  const out: PositionContrib[] = Array.from(map.entries()).map(([ticker, v]) => ({
    ticker,
    contrib: v.contrib,
    nDays: v.nDays,
    hitDays: v.hitDays,
    side:
      v.longDays > 0 && v.shortDays > 0
        ? "both"
        : v.longDays > 0
          ? "long"
          : "short",
  }));
  return out.sort((a, b) => b.contrib - a.contrib);
}

export function PositionContributionPane({ currentRun }: Props) {
  const { locale } = useLocale();

  const all = useMemo<PositionContrib[]>(() => {
    if (!currentRun?.raw.daily_breakdown) return [];
    return aggregateContribution(
      currentRun.raw.daily_breakdown,
      currentRun.raw.train_end_index,
    );
  }, [currentRun]);

  if (!currentRun) {
    return (
      <TmPane title="POSITION.CONTRIBUTION">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }
  if (all.length === 0) {
    return (
      <TmPane title="POSITION.CONTRIBUTION">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const top10 = all.slice(0, 10);
  const bottom10 = all.slice(-10).reverse();
  const totalContrib = all.reduce((a, p) => a + p.contrib, 0);
  const top10Share =
    totalContrib !== 0
      ? top10.reduce((a, p) => a + p.contrib, 0) / totalContrib
      : 0;

  return (
    <TmPane
      title="POSITION.CONTRIBUTION"
      meta={`${all.length} unique tickers · top 10 share ${(top10Share * 100).toFixed(0)}%`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.holdings.contribSubtitle" as Parameters<typeof t>[1])}
      </p>
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2">
        <ContribSide
          title={t(locale, "backtest.holdings.top10Contrib" as Parameters<typeof t>[1])}
          tone="pos"
          rows={top10}
        />
        <ContribSide
          title={t(locale, "backtest.holdings.top10Detract" as Parameters<typeof t>[1])}
          tone="neg"
          rows={bottom10}
        />
      </div>
    </TmPane>
  );
}

function ContribSide({
  title,
  tone,
  rows,
}: {
  readonly title: string;
  readonly tone: "pos" | "neg";
  readonly rows: readonly PositionContrib[];
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
            "32px minmax(80px,100px) 50px minmax(90px,1fr) 60px 60px",
        }}
      >
        <RHeader>#</RHeader>
        <RHeader>ticker</RHeader>
        <RHeader>side</RHeader>
        <RHeader align="right">contrib</RHeader>
        <RHeader align="right">days</RHeader>
        <RHeader align="right">hit %</RHeader>
        {rows.map((p, i) => (
          <ContribRow key={p.ticker} rank={i + 1} pos={p} />
        ))}
      </div>
    </div>
  );
}

function ContribRow({
  rank,
  pos,
}: {
  readonly rank: number;
  readonly pos: PositionContrib;
}) {
  const sideTone =
    pos.side === "long"
      ? "text-tm-pos"
      : pos.side === "short"
        ? "text-tm-neg"
        : "text-tm-fg-2";
  const sideLabel =
    pos.side === "long" ? "L" : pos.side === "short" ? "S" : "L/S";
  const hitPct = pos.nDays > 0 ? (pos.hitDays / pos.nDays) * 100 : 0;
  return (
    <>
      <RCell>
        <span className="text-tm-muted">{String(rank).padStart(2, "0")}</span>
      </RCell>
      <RCell>
        <span className="font-semibold text-tm-accent">{pos.ticker}</span>
      </RCell>
      <RCell>
        <span className={`tabular-nums ${sideTone}`}>{sideLabel}</span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${pos.contrib >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {pos.contrib >= 0 ? "+" : ""}
          {(pos.contrib * 10000).toFixed(1)} bps
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">{pos.nDays}</span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${hitPct > 50 ? "text-tm-pos" : "text-tm-muted"}`}
        >
          {hitPct.toFixed(0)}%
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
