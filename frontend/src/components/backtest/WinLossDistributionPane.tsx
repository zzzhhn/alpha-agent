"use client";

/**
 * WinLossDistributionPane (T6) — daily PnL histogram + 5 KPIs.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 579-700).
 */

import { useMemo } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

const PNL_BINS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: -Infinity, hi: -0.03, label: "<−3%" },
  { lo: -0.03, hi: -0.02, label: "−3..−2" },
  { lo: -0.02, hi: -0.01, label: "−2..−1" },
  { lo: -0.01, hi: -0.005, label: "−1..−0.5" },
  { lo: -0.005, hi: 0, label: "−0.5..0" },
  { lo: 0, hi: 0.005, label: "0..0.5" },
  { lo: 0.005, hi: 0.01, label: "0.5..1" },
  { lo: 0.01, hi: 0.02, label: "1..2" },
  { lo: 0.02, hi: 0.03, label: "2..3" },
  { lo: 0.03, hi: Infinity, label: "≥3%" },
];

export function WinLossDistributionPane({ currentRun }: Props) {
  const { locale } = useLocale();
  const series = useMemo<number[]>(() => {
    if (!currentRun) return [];
    const result = currentRun.raw;
    const bd = result.daily_breakdown;
    if (bd && bd.length > 0) {
      return bd
        .filter((d) => d.long_basket.length > 0 || d.short_basket.length > 0)
        .map((d) => d.daily_return);
    }
    const eq = result.equity_curve;
    const out: number[] = [];
    for (let i = 1; i < eq.length; i++) {
      out.push(eq[i].value / eq[i - 1].value - 1);
    }
    return out;
  }, [currentRun]);

  if (!currentRun) {
    return (
      <TmPane title="WIN/LOSS.DISTRIBUTION">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }
  if (series.length === 0) {
    return (
      <TmPane title="WIN/LOSS.DISTRIBUTION">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const dist = PNL_BINS.map((b) => ({
    label: b.label,
    count: series.filter((v) => v > b.lo && v <= b.hi).length,
    positive: b.lo >= 0,
  }));
  const upDays = series.filter((v) => v > 0).length;
  const downDays = series.filter((v) => v < 0).length;
  const wins = series.filter((v) => v > 0);
  const losses = series.filter((v) => v < 0);
  const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgLoss =
    losses.length > 0 ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const bestDay = series.reduce((m, v) => (v > m ? v : m), -Infinity);
  const worstDay = series.reduce((m, v) => (v < m ? v : m), Infinity);
  const upPct = series.length > 0 ? (upDays / series.length) * 100 : 0;
  const winLossRatio = avgLoss !== 0 ? Math.abs(avgWin / avgLoss) : 0;
  const sumGains = wins.reduce((a, b) => a + b, 0);
  const sumLosses = losses.reduce((a, b) => a + b, 0);
  const profitFactor = sumLosses < 0 ? Math.abs(sumGains / sumLosses) : 0;

  return (
    <TmPane
      title="WIN/LOSS.DISTRIBUTION"
      meta={`${series.length} sessions · ${upDays} up / ${downDays} down`}
    >
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.winLoss.winRate" as Parameters<typeof t>[1])}
          value={`${upPct.toFixed(1)}%`}
          tone={upPct > 50 ? "pos" : "neg"}
          sub={`${upDays}/${series.length}`}
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.bestDay" as Parameters<typeof t>[1])}
          value={`${(bestDay * 100).toFixed(2)}%`}
          tone="pos"
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.worstDay" as Parameters<typeof t>[1])}
          value={`${(worstDay * 100).toFixed(2)}%`}
          tone="neg"
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.avgWin" as Parameters<typeof t>[1])}
          value={`${(avgWin * 100).toFixed(2)}%`}
          tone="pos"
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.avgLoss" as Parameters<typeof t>[1])}
          value={`${(avgLoss * 100).toFixed(2)}%`}
          tone="neg"
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.ratio" as Parameters<typeof t>[1])}
          value={winLossRatio.toFixed(2)}
          tone={winLossRatio > 1 ? "pos" : "neg"}
          sub={t(locale, "backtest.winLoss.ratioHint" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.winLoss.profitFactor" as Parameters<typeof t>[1])}
          value={profitFactor.toFixed(2)}
          tone={profitFactor > 1 ? "pos" : "neg"}
          sub={t(locale, "backtest.winLoss.profitFactorHint" as Parameters<typeof t>[1])}
        />
      </TmKpiGrid>
      <div className="h-[180px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dist} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="2 4"
              stroke="var(--tm-rule)"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              interval={0}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)"
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
            />
            <Bar dataKey="count">
              {dist.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.positive ? "var(--tm-pos)" : "var(--tm-neg)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

function UnavailableMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[120px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}
