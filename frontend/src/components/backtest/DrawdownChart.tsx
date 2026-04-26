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
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { EquityCurvePoint } from "@/lib/types";

interface DrawdownChartProps {
  readonly equityCurve: readonly EquityCurvePoint[];
}

interface UnderwaterPoint {
  readonly date: string;
  readonly drawdown: number;   // percent, negative or zero
}

// Underwater curve = (equity - cummax(equity)) / cummax(equity).
// Computed entirely on the client to avoid a second backend round-trip;
// the equity curve is already in scope from the prior factor backtest call.
function buildUnderwater(eq: readonly EquityCurvePoint[]): UnderwaterPoint[] {
  if (eq.length === 0) return [];
  const out: UnderwaterPoint[] = [];
  let peak = eq[0].value;
  for (const p of eq) {
    if (p.value > peak) peak = p.value;
    const dd = peak > 0 ? (p.value - peak) / peak : 0;
    out.push({ date: p.date, drawdown: dd * 100 });
  }
  return out;
}

export function DrawdownChart({ equityCurve }: DrawdownChartProps) {
  const { locale } = useLocale();
  const data = buildUnderwater(equityCurve);
  const minDD = data.length > 0 ? Math.min(...data.map((p) => p.drawdown)) : 0;

  return (
    <Card padding="md">
      <header className="mb-2 flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text">
            {t(locale, "backtest.drawdown.title")}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-muted">
            {t(locale, "backtest.drawdown.subtitle")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[10px] uppercase tracking-wide text-muted">
            {t(locale, "backtest.drawdown.worst")}
          </div>
          <div className="font-mono text-base font-semibold text-red">
            {minDD.toFixed(2)}%
          </div>
        </div>
      </header>

      <div className="h-[200px] w-full">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--red, #ef4444)" stopOpacity={0.05} />
                <stop offset="100%" stopColor="var(--red, #ef4444)" stopOpacity={0.55} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              domain={["auto", 0]}
            />
            <Tooltip
              contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--border)", fontSize: 11 }}
              formatter={(v) => (typeof v === "number" ? `${v.toFixed(2)}%` : String(v ?? ""))}
            />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke="var(--red, #ef4444)"
              strokeWidth={1.5}
              fill="url(#ddGrad)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
