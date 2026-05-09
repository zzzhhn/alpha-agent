"use client";

/**
 * TmCompareEquityChart — workstation port of CompareEquityChart.
 *
 * 3-line overlay: factor1 (tm-accent), factor2 (tm-info), benchmark
 * (tm-muted dashed). All three series normalized to base=100 at the
 * first common date so the visual is fair regardless of starting
 * capital. Used only on /report's compare panel.
 */

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

interface TmCompareEquityChartProps {
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

function mergeAndNormalize(
  f1: readonly EquityCurvePoint[],
  f2: readonly EquityCurvePoint[],
  bm: readonly EquityCurvePoint[],
): MergedRow[] {
  const map1 = new Map(f1.map((p) => [p.date, p.value]));
  const map2 = new Map(f2.map((p) => [p.date, p.value]));
  const mapB = new Map(bm.map((p) => [p.date, p.value]));
  const dates = bm.map((p) => p.date);
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

export function TmCompareEquityChart({
  factor1Name,
  factor1,
  factor2Name,
  factor2,
  benchmark,
  benchmarkTicker,
  height = 320,
}: TmCompareEquityChartProps) {
  const data = mergeAndNormalize(factor1, factor2, benchmark);

  return (
    <div className="w-full px-1 pb-2 pt-2" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
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
            tickFormatter={(v: number) => v.toFixed(0)}
            domain={["dataMin", "dataMax"]}
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
              typeof v === "number" ? v.toFixed(1) : String(v ?? "")
            }
          />
          <Legend
            wrapperStyle={{
              fontSize: 11,
              fontFamily: "var(--font-jetbrains-mono)",
            }}
          />
          <ReferenceLine y={100} stroke="var(--tm-rule-2)" strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey="factor1"
            name={factor1Name}
            stroke="var(--tm-accent)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="factor2"
            name={factor2Name}
            stroke="var(--tm-info)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            name={benchmarkTicker}
            stroke="var(--tm-muted)"
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
