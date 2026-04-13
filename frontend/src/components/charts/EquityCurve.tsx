"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import type { EquityCurvePoint } from "@/lib/types";

interface EquityCurveProps {
  readonly data: readonly EquityCurvePoint[];
  readonly initialCapital?: number;
}

export function EquityCurve({
  data,
  initialCapital = 100000,
}: EquityCurveProps) {
  if (data.length === 0) return null;

  const finalValue = data[data.length - 1]?.value ?? initialCapital;
  const isProfit = finalValue >= initialCapital;

  // Format data for recharts (needs mutable array)
  const chartData = data.map((d) => ({
    date: d.date,
    value: d.value,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="5%"
              stopColor={isProfit ? "var(--green)" : "var(--red)"}
              stopOpacity={0.3}
            />
            <stop
              offset="95%"
              stopColor={isProfit ? "var(--green)" : "var(--red)"}
              stopOpacity={0}
            />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.3} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "var(--muted)" }}
          tickFormatter={(v: string) => v.slice(5)}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--muted)" }}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(v) => [`$${Number(v).toLocaleString()}`, "Portfolio"]}
          labelFormatter={(l) => String(l)}
        />
        <ReferenceLine
          y={initialCapital}
          stroke="var(--muted)"
          strokeDasharray="3 3"
          label={{ value: "Initial", fill: "var(--muted)", fontSize: 10 }}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={isProfit ? "var(--green)" : "var(--red)"}
          strokeWidth={2}
          fill="url(#equityGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
