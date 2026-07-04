"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { PnlPoint } from "@/lib/api/brain";

// Cumulative-PnL curve for a mined alpha, in the workstation's terminal palette
// (CSS vars, not Material colours) so it matches the rest of AlphaCore.
export function BrainPnLChart({
  points,
  height = 220,
}: {
  readonly points: PnlPoint[];
  readonly height?: number;
}) {
  if (points.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.25} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 9, fill: "var(--muted)" }}
          tickFormatter={(v: string) => (typeof v === "string" ? v.slice(0, 7) : v)}
          interval="preserveStartEnd"
          minTickGap={40}
        />
        <YAxis
          tick={{ fontSize: 9, fill: "var(--muted)" }}
          tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
          domain={["auto", "auto"]}
          width={38}
        />
        <Tooltip
          contentStyle={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 11,
            fontFamily: "var(--font-tm-mono, monospace)",
          }}
          labelStyle={{ color: "var(--muted)" }}
          formatter={(v) => [
            typeof v === "number"
              ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
              : String(v),
            "PnL",
          ]}
        />
        <Line
          type="monotone"
          dataKey="pnl"
          stroke="var(--accent, #34d399)"
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
