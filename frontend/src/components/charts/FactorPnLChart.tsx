"use client";

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
import type { FactorBacktestResponse } from "@/lib/types";

interface FactorPnLChartProps {
  readonly data: FactorBacktestResponse;
  readonly height?: number;
}

interface MergedPoint {
  readonly date: string;
  readonly factor: number;
  readonly benchmark: number;
}

function mergeCurves(
  equity: FactorBacktestResponse["equity_curve"],
  benchmark: FactorBacktestResponse["benchmark_curve"],
): MergedPoint[] {
  const byDate = new Map<string, { factor?: number; benchmark?: number }>();
  for (const p of equity) {
    byDate.set(p.date, { ...(byDate.get(p.date) ?? {}), factor: p.value });
  }
  for (const p of benchmark) {
    byDate.set(p.date, {
      ...(byDate.get(p.date) ?? {}),
      benchmark: p.value,
    });
  }
  return Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, v]) => ({
      date,
      factor: v.factor ?? NaN,
      benchmark: v.benchmark ?? NaN,
    }));
}

function currencyLabel(code: string): string {
  if (code === "USD") return "$";
  if (code === "CNY") return "¥";
  if (code === "EUR") return "€";
  return `${code} `;
}

function formatCurrency(value: number, code: string): string {
  const sym = currencyLabel(code);
  return `${sym}${value.toLocaleString(undefined, {
    maximumFractionDigits: 0,
  })}`;
}

export function FactorPnLChart({ data, height = 340 }: FactorPnLChartProps) {
  const merged = mergeCurves(data.equity_curve, data.benchmark_curve);
  if (merged.length === 0) return null;

  const sym = currencyLabel(data.currency);
  const splitDate = merged[data.train_end_index]?.date ?? "";
  const firstDate = merged[0]?.date ?? "";
  const lastDate = merged[merged.length - 1]?.date ?? "";

  // Midpoints for "Train" / "Test" text labels below the X axis.
  const trainMidIdx = Math.max(0, Math.floor(data.train_end_index / 2));
  const testMidIdx = Math.min(
    merged.length - 1,
    data.train_end_index +
      Math.floor((merged.length - data.train_end_index) / 2),
  );
  const trainMidDate = merged[trainMidIdx]?.date ?? firstDate;
  const testMidDate = merged[testMidIdx]?.date ?? lastDate;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart
        data={merged}
        margin={{ top: 20, right: 24, left: 8, bottom: 36 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="var(--border)"
          opacity={0.3}
        />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "var(--muted)" }}
          tickFormatter={(v: string) => v.slice(5)}
          interval="preserveStartEnd"
          minTickGap={32}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--muted)" }}
          tickFormatter={(v: number) => `${sym}${(v / 1000).toFixed(0)}k`}
          domain={["auto", "auto"]}
          label={{
            value: `P&L (${data.currency})`,
            angle: -90,
            position: "insideLeft",
            fill: "var(--muted)",
            fontSize: 11,
            dy: 40,
          }}
        />
        <Tooltip
          contentStyle={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(value, name) => {
            const num = typeof value === "number" ? value : Number(value);
            const label =
              name === "factor"
                ? data.factor_name
                : data.benchmark_ticker;
            return [formatCurrency(num, data.currency), label];
          }}
          labelFormatter={(l) => String(l)}
        />
        <Legend
          align="right"
          verticalAlign="top"
          iconType="plainline"
          wrapperStyle={{ fontSize: 12, paddingBottom: 4 }}
          formatter={(value) =>
            value === "factor" ? data.factor_name : data.benchmark_ticker
          }
        />
        {splitDate ? (
          <ReferenceLine
            x={splitDate}
            stroke="var(--muted)"
            strokeDasharray="4 3"
            label={{
              value: "Train | Test",
              position: "top",
              fill: "var(--muted)",
              fontSize: 10,
            }}
          />
        ) : null}
        {/* Train / Test text labels below the X axis, via invisible
            ReferenceLines positioned at split midpoints. */}
        <ReferenceLine
          x={trainMidDate}
          stroke="transparent"
          label={{
            value: "Train",
            position: "insideBottom",
            fill: "var(--muted)",
            fontSize: 11,
            dy: 18,
          }}
        />
        <ReferenceLine
          x={testMidDate}
          stroke="transparent"
          label={{
            value: "Test",
            position: "insideBottom",
            fill: "var(--muted)",
            fontSize: 11,
            dy: 18,
          }}
        />
        <Line
          type="monotone"
          dataKey="factor"
          name="factor"
          stroke="var(--accent, #60a5fa)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="benchmark"
          name="benchmark"
          stroke="var(--muted-strong, #94a3b8)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
