"use client";

/**
 * TurnoverProfilePane (T6) — histogram of daily turnover + roll-in/out KPIs.
 * Chart logic lifted from (dashboard)/backtest/page.tsx (lines 826-930).
 *
 * Requires `daily_breakdown` on the response.
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

export function TurnoverProfilePane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="TURNOVER.PROFILE">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }

  const breakdown = currentRun.raw.daily_breakdown;
  if (!breakdown || breakdown.length === 0) {
    return (
      <TmPane title="TURNOVER.PROFILE">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  if (populated.length < 2) {
    return (
      <TmPane title="TURNOVER.PROFILE">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const turnovers: number[] = [];
  let totalRolledIn = 0;
  let totalRolledOut = 0;
  for (let i = 1; i < populated.length; i++) {
    const prev = populated[i - 1];
    const curr = populated[i];
    const wPrev = new Map<string, number>();
    for (const e of prev.long_basket) wPrev.set(e.ticker, e.weight);
    for (const e of prev.short_basket) wPrev.set(e.ticker, -e.weight);
    const wCurr = new Map<string, number>();
    for (const e of curr.long_basket) wCurr.set(e.ticker, e.weight);
    for (const e of curr.short_basket) wCurr.set(e.ticker, -e.weight);
    let l1 = 0;
    const allKeys = new Set<string>([
      ...Array.from(wPrev.keys()),
      ...Array.from(wCurr.keys()),
    ]);
    Array.from(allKeys).forEach((k) => {
      l1 += Math.abs((wCurr.get(k) ?? 0) - (wPrev.get(k) ?? 0));
    });
    turnovers.push(l1 / 2);
    const prevSet = new Set<string>(Array.from(wPrev.keys()));
    const currSet = new Set<string>(Array.from(wCurr.keys()));
    Array.from(currSet).forEach((k) => {
      if (!prevSet.has(k)) totalRolledIn++;
    });
    Array.from(prevSet).forEach((k) => {
      if (!currSet.has(k)) totalRolledOut++;
    });
  }
  const avgTurnover =
    turnovers.length > 0
      ? turnovers.reduce((a, b) => a + b, 0) / turnovers.length
      : 0;
  const days = turnovers.length;
  const avgRolledIn = days > 0 ? totalRolledIn / days : 0;
  const avgRolledOut = days > 0 ? totalRolledOut / days : 0;

  const maxT = Math.max(...turnovers, 0.01);
  const binEdges = Array.from({ length: 9 }, (_, i) => (i / 8) * maxT);
  const dist = Array.from({ length: 8 }, (_, i) => {
    const lo = binEdges[i];
    const hi = binEdges[i + 1];
    return {
      label: `${(lo * 100).toFixed(0)}-${(hi * 100).toFixed(0)}%`,
      count: turnovers.filter((v) => v >= lo && (i === 7 ? v <= hi : v < hi))
        .length,
    };
  });

  return (
    <TmPane
      title="TURNOVER.PROFILE"
      meta={`avg ${(avgTurnover * 100).toFixed(0)}% / day · ${days} sessions`}
    >
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.turnover.avg" as Parameters<typeof t>[1])}
          value={`${(avgTurnover * 100).toFixed(0)}%`}
          tone={avgTurnover > 0.5 ? "warn" : "default"}
          sub={t(locale, "backtest.turnover.avgHint" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.turnover.rolledIn" as Parameters<typeof t>[1])}
          value={avgRolledIn.toFixed(1)}
          sub={t(locale, "backtest.turnover.rolledInHint" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.turnover.rolledOut" as Parameters<typeof t>[1])}
          value={avgRolledOut.toFixed(1)}
          sub={t(locale, "backtest.turnover.rolledOutHint" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.turnover.cost5bps" as Parameters<typeof t>[1])}
          value={`${(((avgTurnover * 5 * 252) / 10000) * 100).toFixed(2)}%`}
          tone="warn"
          sub={t(locale, "backtest.turnover.cost5bpsHint" as Parameters<typeof t>[1])}
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
            <Bar dataKey="count" fill="var(--tm-info)" />
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
