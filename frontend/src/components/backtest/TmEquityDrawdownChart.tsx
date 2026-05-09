"use client";

/**
 * TmEquityDrawdownChart — combined equity + underwater chart (v3).
 *
 * Replaces the v2 layout's separate EQUITY.CURVE + DRAWDOWN.UNDERWATER
 * panes with a single ComposedChart:
 *   - Left y-axis: equity index (factor + benchmark lines)
 *   - Right y-axis: drawdown % (red area, 0 → negative)
 *
 * Lets a user see both signals (was the curve smooth or jagged? where
 * did the worst drawdown happen and how long did it take to recover?)
 * in one glance, saving ~220px vertical vs two stacked panes.
 *
 * Pattern borrowed from Bloomberg PORT and AQR factor-research figures
 * which routinely overlay an underwater plot below the cumulative
 * equity line on a shared time axis.
 */

import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";
import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { FactorBacktestResponse } from "@/lib/types";

interface MergedPoint {
  readonly date: string;
  readonly factor: number;
  readonly benchmark: number;
  readonly drawdown: number; // percent, negative or zero
}

function buildSeries(
  equity: FactorBacktestResponse["equity_curve"],
  benchmark: FactorBacktestResponse["benchmark_curve"],
): MergedPoint[] {
  if (equity.length === 0) return [];

  const factorBase = equity[0].value || 1;
  const benchBase = benchmark[0]?.value || 1;
  const benchMap = new Map<string, number>();
  for (const p of benchmark) benchMap.set(p.date, p.value);

  let peak = equity[0].value;
  const out: MergedPoint[] = [];
  for (const p of equity) {
    if (p.value > peak) peak = p.value;
    const dd = peak > 0 ? ((p.value - peak) / peak) * 100 : 0;
    const benchVal = benchMap.get(p.date);
    out.push({
      date: p.date,
      factor: p.value / factorBase,
      benchmark: benchVal !== undefined ? benchVal / benchBase : 1,
      drawdown: dd,
    });
  }
  return out;
}

export function TmEquityDrawdownChart({
  result,
  height = 380,
}: {
  readonly result: FactorBacktestResponse;
  readonly height?: number;
}) {
  const { locale } = useLocale();
  const data = buildSeries(result.equity_curve, result.benchmark_curve);
  const minDD =
    data.length > 0 ? Math.min(...data.map((p) => p.drawdown)) : 0;
  const factorEnd = data.length > 0 ? data[data.length - 1].factor : 1;
  const benchEnd = data.length > 0 ? data[data.length - 1].benchmark : 1;

  return (
    <TmPane
      title="EQUITY.UNDERWATER"
      meta={
        data.length > 0
          ? `factor ${((factorEnd - 1) * 100).toFixed(1)}% · bench ${((benchEnd - 1) * 100).toFixed(1)}% · worst DD ${minDD.toFixed(1)}%`
          : undefined
      }
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.equity.subtitle")} · drawdown overlay on
        secondary axis.
      </p>
      <div className="w-full px-1 pb-2 pt-2" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="tm-eq-dd-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--tm-neg)" stopOpacity={0.05} />
                <stop offset="100%" stopColor="var(--tm-neg)" stopOpacity={0.45} />
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
              yAxisId="eq"
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              tickFormatter={(v: number) => v.toFixed(2)}
              stroke="var(--tm-rule)"
              domain={["auto", "auto"]}
            />
            <YAxis
              yAxisId="dd"
              orientation="right"
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              stroke="var(--tm-rule)"
              domain={["auto", 0]}
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
              formatter={(v, name) =>
                typeof v === "number"
                  ? name === "drawdown"
                    ? `${v.toFixed(2)}%`
                    : v.toFixed(3)
                  : String(v ?? "")
              }
            />
            <Legend
              wrapperStyle={{
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
              }}
            />
            <ReferenceLine
              yAxisId="eq"
              y={1}
              stroke="var(--tm-rule-2)"
              strokeWidth={1}
            />
            <Area
              yAxisId="dd"
              type="monotone"
              dataKey="drawdown"
              name="drawdown"
              stroke="var(--tm-neg)"
              strokeWidth={1.2}
              fill="url(#tm-eq-dd-grad)"
              isAnimationActive={false}
            />
            <Line
              yAxisId="eq"
              type="monotone"
              dataKey="benchmark"
              name="benchmark"
              stroke="var(--tm-muted)"
              strokeWidth={1.5}
              dot={false}
              strokeDasharray="3 3"
              isAnimationActive={false}
            />
            <Line
              yAxisId="eq"
              type="monotone"
              dataKey="factor"
              name="factor"
              stroke="var(--tm-accent)"
              strokeWidth={1.8}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
