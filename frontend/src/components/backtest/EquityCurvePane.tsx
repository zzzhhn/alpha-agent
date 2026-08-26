"use client";

/**
 * EquityCurvePane — default evidence pane #1 for /backtest redesign (T5).
 *
 * 4-state lifecycle: waiting / loading (running) / ok / error.
 * Chart logic lifted from TmEquityDrawdownChart but reduced to a pure
 * equity-vs-benchmark line chart (drawdown gets its own pane below).
 */

import { useMemo } from "react";
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
import { TmPane } from "@/components/tm/TmPane";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { EquityCurvePoint } from "@/lib/types";
import type { Run, RunState } from "./types";
import { TM_CHART_CSS } from "@/components/charts";

interface Props {
  readonly runState: RunState;
  readonly currentRun: Run | null;
}

interface MergedPoint {
  readonly date: string;
  readonly factor: number;
  readonly benchmark: number;
}

function buildSeries(
  equity: readonly EquityCurvePoint[],
  benchmark: readonly EquityCurvePoint[],
): MergedPoint[] {
  if (equity.length === 0) return [];
  const factorBase = equity[0].value || 1;
  const benchBase = benchmark[0]?.value || 1;
  const benchMap = new Map<string, number>();
  for (const p of benchmark) benchMap.set(p.date, p.value);

  const out: MergedPoint[] = [];
  for (const p of equity) {
    const benchVal = benchMap.get(p.date);
    out.push({
      date: p.date,
      factor: p.value / factorBase,
      benchmark: benchVal !== undefined ? benchVal / benchBase : 1,
    });
  }
  return out;
}

export function EquityCurvePane({ runState, currentRun }: Props) {
  const { locale } = useLocale();
  const title = t(locale, "backtest.evidence.equity");

  const data = useMemo(() => {
    if (!currentRun) return [] as MergedPoint[];
    return buildSeries(
      currentRun.raw.equity_curve,
      currentRun.raw.benchmark_curve,
    );
  }, [currentRun]);

  if (runState.kind === "running") {
    return (
      <TmPane title={title}>
        <TmStatePane
          state="loading"
          title={title}
          description={t(locale, "backtest.evidence.waiting")}
          className="min-h-[220px] rounded-none border-0"
        />
      </TmPane>
    );
  }
  if (runState.kind === "error") {
    // Detail lives in <BacktestVerdictBar/>. Panes show a minimal pointer
    // so the same 422 message isn't repeated 3+ times down the page.
    return (
      <TmPane title={title}>
        <TmStatePane
          state="error"
          title={t(locale, "backtest.evidence.errorPlaceholder")}
          className="min-h-[220px] rounded-none border-0"
        />
      </TmPane>
    );
  }
  if (!currentRun || data.length === 0) {
    return (
      <TmPane title={title}>
        <TmStatePane
          state="empty"
          title={
            currentRun
              ? t(locale, "backtest.evidence.unavailable")
              : t(locale, "backtest.evidence.waiting")
          }
          className="min-h-[220px] rounded-none border-0"
        />
      </TmPane>
    );
  }

  const last = data[data.length - 1];
  const factorPct = ((last.factor - 1) * 100).toFixed(1);
  const benchPct = ((last.benchmark - 1) * 100).toFixed(1);

  return (
    <TmPane title={title} meta={`factor ${factorPct}% · bench ${benchPct}%`}>
      <div className="w-full px-1 pb-2 pt-2" style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={TM_CHART_CSS.grid} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: TM_CHART_CSS.muted }}
              interval="preserveStartEnd"
              minTickGap={40}
              stroke={TM_CHART_CSS.grid}
            />
            <YAxis
              tick={{ fontSize: 12, fill: TM_CHART_CSS.muted }}
              tickFormatter={(v: number) => v.toFixed(2)}
              stroke={TM_CHART_CSS.grid}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                background: TM_CHART_CSS.surface,
                border: `1px solid ${TM_CHART_CSS.grid}`,
                fontSize: 12,
                fontFamily: "var(--font-jetbrains-mono)",
                color: TM_CHART_CSS.foreground,
              }}
              formatter={(v) =>
                typeof v === "number" ? v.toFixed(3) : String(v ?? "")
              }
            />
            <Legend
              wrapperStyle={{
                fontSize: 12,
                fontFamily: "var(--font-jetbrains-mono)",
              }}
            />
            <ReferenceLine y={1} stroke={TM_CHART_CSS.gridStrong} strokeWidth={1} />
            <Line
              type="monotone"
              dataKey="benchmark"
              name={t(locale, "backtest.evidence.benchmark")}
              stroke={TM_CHART_CSS.muted}
              strokeWidth={1.5}
              dot={false}
              strokeDasharray="3 3"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="factor"
              name={t(locale, "backtest.evidence.factor")}
              stroke={TM_CHART_CSS.positive}
              strokeWidth={1.8}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
