"use client";

import { useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import type { IcTrendSeries } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";

interface IcTrendChartProps {
  readonly series: IcTrendSeries[];
  readonly locale: Locale;
}

// One color per signal, cycling through tm vars then fallback hex values.
const SIGNAL_COLORS = [
  "var(--tm-accent)",
  "var(--tm-info)",
  "var(--tm-pos, #10b981)",
  "var(--tm-warn, #f59e0b)",
  "var(--tm-neg, #f87171)",
  "#a78bfa",
  "#38bdf8",
];

function shortDate(iso: string): string {
  // "2025-03-15T00:00:00" → "03-15"
  return iso.slice(5, 10);
}

interface MergedRow {
  readonly date: string;
  [signalName: string]: number | string;
}

function mergeIcSeries(series: IcTrendSeries[]): MergedRow[] {
  // Collect all unique timestamps across all signals.
  const dateSet = new Set<string>();
  for (const s of series) {
    for (const p of s.points) {
      dateSet.add(p.computed_at);
    }
  }
  const sortedDates = Array.from(dateSet).sort();
  if (sortedDates.length === 0) return [];

  // Build per-signal lookup maps.
  const maps = series.map((s) => {
    const m = new Map<string, number>();
    for (const p of s.points) {
      m.set(p.computed_at, p.ic);
    }
    return m;
  });

  return sortedDates.map((date) => {
    const row: MergedRow = { date: shortDate(date) };
    series.forEach((s, i) => {
      const v = maps[i].get(date);
      if (v !== undefined) {
        row[s.signal_name] = v;
      }
    });
    return row;
  });
}

export function IcTrendChart({ series, locale }: IcTrendChartProps) {
  const hasData = series.length > 0 && series.some((s) => s.points.length > 0);

  const merged = useMemo(() => mergeIcSeries(series), [series]);

  if (!hasData || merged.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-muted text-center">
        {t(locale, "evolution.ic.empty")}
      </p>
    );
  }

  return (
    <div className="w-full px-1 pb-2 pt-2" style={{ height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
            interval="preserveStartEnd"
            minTickGap={40}
            stroke="var(--tm-rule)"
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
            tickFormatter={(v: number) => v.toFixed(2)}
            domain={["auto", "auto"]}
            stroke="var(--tm-rule)"
          />
          <Tooltip
            contentStyle={{
              background: "var(--tm-bg-2)",
              border: "1px solid var(--tm-rule)",
              fontSize: 11,
              fontFamily: "var(--font-jetbrains-mono)",
              color: "var(--tm-fg)",
            }}
            formatter={(v) =>
              typeof v === "number" ? v.toFixed(4) : String(v ?? "")
            }
          />
          <Legend
            wrapperStyle={{
              fontSize: 11,
              fontFamily: "var(--font-jetbrains-mono)",
            }}
          />
          <ReferenceLine
            y={0}
            stroke="var(--tm-rule-2)"
            strokeDasharray="4 4"
          />
          {series.map((s, i) => (
            <Line
              key={s.signal_name}
              type="monotone"
              dataKey={s.signal_name}
              name={getSignalDisplayLabel(s.signal_name, locale)}
              stroke={SIGNAL_COLORS[i % SIGNAL_COLORS.length]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
