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
} from "recharts";
import type { PnlPoint } from "@/lib/api/brain";

export type ChartKind = "pnl" | "sharpe" | "drawdown";

// All three curves are DERIVED from the single PnL series BRAIN returns — no
// extra endpoints. Rendered in the workstation's terminal palette (CSS vars).
function deriveSeries(points: PnlPoint[], kind: ChartKind) {
  if (kind === "pnl") {
    return points.map((p) => ({ date: p.date, value: p.pnl }));
  }
  // daily PnL change series
  const daily: { date: string; d: number }[] = [];
  for (let i = 1; i < points.length; i++) {
    daily.push({ date: points[i].date, d: points[i].pnl - points[i - 1].pnl });
  }
  if (kind === "drawdown") {
    // running peak of cumulative PnL, drawdown = cum - peak (<= 0)
    let peak = -Infinity;
    return points.map((p) => {
      peak = Math.max(peak, p.pnl);
      return { date: p.date, value: p.pnl - peak };
    });
  }
  // rolling annualized Sharpe over a ~63-day (quarter) window
  const W = 63;
  const out: { date: string; value: number }[] = [];
  for (let i = 0; i < daily.length; i++) {
    const s = Math.max(0, i - W + 1);
    const win = daily.slice(s, i + 1).map((x) => x.d);
    if (win.length < 10) continue;
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    const variance = win.reduce((a, b) => a + (b - mean) ** 2, 0) / win.length;
    const sd = Math.sqrt(variance);
    out.push({ date: daily[i].date, value: sd > 1e-9 ? (mean / sd) * Math.sqrt(252) : 0 });
  }
  return out;
}

export function BrainPnLChart({
  points,
  kind = "pnl",
  height = 220,
}: {
  readonly points: PnlPoint[];
  readonly kind?: ChartKind;
  readonly height?: number;
}) {
  const data = useMemo(() => deriveSeries(points, kind), [points, kind]);
  if (data.length === 0) return null;

  const yFmt =
    kind === "sharpe"
      ? (v: number) => v.toFixed(1)
      : (v: number) => `${(v / 1000).toFixed(0)}k`;
  const stroke =
    kind === "drawdown" ? "var(--tm-neg, #f87171)" : "var(--accent, #34d399)";

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
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
          tickFormatter={(v: number) => yFmt(v)}
          domain={["auto", "auto"]}
          width={40}
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
            typeof v === "number" ? yFmt(v) : String(v),
            kind === "sharpe" ? "Sharpe" : kind === "drawdown" ? "DD" : "PnL",
          ]}
        />
        <Line type="monotone" dataKey="value" stroke={stroke} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
