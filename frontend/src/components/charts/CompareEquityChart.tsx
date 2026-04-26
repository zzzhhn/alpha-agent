"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";
import type { EquityCurvePoint } from "@/lib/types";

interface CompareEquityChartProps {
  readonly factor1Name: string;
  readonly factor1: readonly EquityCurvePoint[];
  readonly factor2Name: string;
  readonly factor2: readonly EquityCurvePoint[];
  readonly benchmark: readonly EquityCurvePoint[];
  readonly benchmarkTicker: string;
  readonly height?: number;
}

interface MergedRow {
  readonly date: string;
  readonly factor1: number;
  readonly factor2: number;
  readonly benchmark: number;
}

// Normalize all three series to base 100 at the first common date so the
// overlay is visually fair regardless of starting capital.
function mergeAndNormalize(
  f1: readonly EquityCurvePoint[],
  f2: readonly EquityCurvePoint[],
  bm: readonly EquityCurvePoint[],
): MergedRow[] {
  const map1 = new Map(f1.map((p) => [p.date, p.value]));
  const map2 = new Map(f2.map((p) => [p.date, p.value]));
  const mapB = new Map(bm.map((p) => [p.date, p.value]));
  const dates = bm.map((p) => p.date);   // benchmark drives the timeline
  if (dates.length === 0) return [];

  const base1 = map1.get(dates[0]) ?? f1[0]?.value ?? 1;
  const base2 = map2.get(dates[0]) ?? f2[0]?.value ?? 1;
  const baseB = mapB.get(dates[0]) ?? bm[0]?.value ?? 1;

  return dates.map((d) => ({
    date: d,
    factor1: ((map1.get(d) ?? base1) / base1) * 100,
    factor2: ((map2.get(d) ?? base2) / base2) * 100,
    benchmark: ((mapB.get(d) ?? baseB) / baseB) * 100,
  }));
}

export function CompareEquityChart({
  factor1Name, factor1, factor2Name, factor2, benchmark, benchmarkTicker, height = 280,
}: CompareEquityChartProps) {
  const data = mergeAndNormalize(factor1, factor2, benchmark);

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--muted)" }}
            tickFormatter={(v: number) => v.toFixed(0)}
            domain={["dataMin", "dataMax"]}
          />
          <Tooltip
            contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--border)", fontSize: 11 }}
            formatter={(v) => (typeof v === "number" ? v.toFixed(1) : String(v ?? ""))}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <ReferenceLine y={100} stroke="var(--border)" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="factor1"
            name={factor1Name}
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="factor2"
            name={factor2Name}
            stroke="#a855f7"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            name={benchmarkTicker}
            stroke="var(--muted)"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
