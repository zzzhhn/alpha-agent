"use client";

/**
 * TmDrawdownChart — workstation port of DrawdownChart.
 *
 * Underwater equity curve as an AreaChart. Computed client-side from
 * the equity_curve already in scope (no second backend round-trip).
 * Theme: tm-neg (terminal red) + gradient fill, tm-rule grid + axes,
 * tm-bg-2 tooltip.
 *
 * Worst drawdown summary moves into the pane meta strip; legacy showed
 * it as a right-aligned pill in the card header.
 */

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
import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { EquityCurvePoint } from "@/lib/types";

interface UnderwaterPoint {
  readonly date: string;
  readonly drawdown: number;
}

function buildUnderwater(
  eq: readonly EquityCurvePoint[],
): UnderwaterPoint[] {
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

export function TmDrawdownChart({
  equityCurve,
}: {
  readonly equityCurve: readonly EquityCurvePoint[];
}) {
  const { locale } = useLocale();
  const data = buildUnderwater(equityCurve);
  const minDD =
    data.length > 0 ? Math.min(...data.map((p) => p.drawdown)) : 0;

  return (
    <TmPane
      title="DRAWDOWN.UNDERWATER"
      meta={`worst ${minDD.toFixed(2)}% · ${data.length} sessions`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.drawdown.subtitle")}
      </p>
      <div className="h-[220px] w-full px-1 pb-2 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 6, right: 16, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="tm-dd-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--tm-neg)" stopOpacity={0.05} />
                <stop offset="100%" stopColor="var(--tm-neg)" stopOpacity={0.55} />
              </linearGradient>
            </defs>
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
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              domain={["auto", 0]}
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
                typeof v === "number" ? `${v.toFixed(2)}%` : String(v ?? "")
              }
            />
            <ReferenceLine y={0} stroke="var(--tm-rule-2)" />
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke="var(--tm-neg)"
              strokeWidth={1.5}
              fill="url(#tm-dd-grad)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
