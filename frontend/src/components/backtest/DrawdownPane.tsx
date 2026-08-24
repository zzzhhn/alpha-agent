"use client";

/**
 * DrawdownPane — default evidence pane #2 for /backtest redesign (T5).
 *
 * 4-state lifecycle: waiting / loading / ok / error.
 * Chart logic lifted from TmDrawdownChart — underwater drawdown area
 * derived from equity_curve. Worst drawdown date + magnitude annotated
 * inline in the pane meta strip.
 */

import { useMemo } from "react";
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

interface UnderwaterPoint {
  readonly date: string;
  readonly drawdown: number;   // percent, <= 0
}

interface BuildOutput {
  readonly points: UnderwaterPoint[];
  readonly worstDate: string | null;
  readonly worstDD: number;
}

function buildUnderwater(eq: readonly EquityCurvePoint[]): BuildOutput {
  if (eq.length === 0) {
    return { points: [], worstDate: null, worstDD: 0 };
  }
  const points: UnderwaterPoint[] = [];
  let peak = eq[0].value;
  let worstDD = 0;
  let worstDate: string | null = null;
  for (const p of eq) {
    if (p.value > peak) peak = p.value;
    const dd = peak > 0 ? ((p.value - peak) / peak) * 100 : 0;
    if (dd < worstDD) {
      worstDD = dd;
      worstDate = p.date;
    }
    points.push({ date: p.date, drawdown: dd });
  }
  return { points, worstDate, worstDD };
}

export function DrawdownPane({ runState, currentRun }: Props) {
  const { locale } = useLocale();
  const title = t(locale, "backtest.evidence.drawdown");

  const built = useMemo<BuildOutput>(() => {
    if (!currentRun) return { points: [], worstDate: null, worstDD: 0 };
    return buildUnderwater(currentRun.raw.equity_curve);
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
  if (!currentRun || built.points.length === 0) {
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

  const worstLabel = built.worstDate
    ? `${t(locale, "backtest.evidence.worstDrawdown")} ${built.worstDD.toFixed(2)}% · ${built.worstDate}`
    : `${t(locale, "backtest.evidence.worstDrawdown")} ${built.worstDD.toFixed(2)}%`;

  return (
    <TmPane title={title} meta={worstLabel}>
      <div className="w-full px-1 pb-2 pt-2" style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={built.points}
            margin={{ top: 6, right: 16, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id="bt-pane-dd-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={TM_CHART_CSS.negative} stopOpacity={0.05} />
                <stop offset="100%" stopColor={TM_CHART_CSS.negative} stopOpacity={0.55} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="2 4" stroke={TM_CHART_CSS.grid} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: TM_CHART_CSS.muted }}
              interval="preserveStartEnd"
              minTickGap={40}
              stroke={TM_CHART_CSS.grid}
            />
            <YAxis
              tick={{ fontSize: 10, fill: TM_CHART_CSS.muted }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              domain={["auto", 0]}
              stroke={TM_CHART_CSS.grid}
            />
            <Tooltip
              contentStyle={{
                background: TM_CHART_CSS.surface,
                border: `1px solid ${TM_CHART_CSS.grid}`,
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: TM_CHART_CSS.foreground,
              }}
              formatter={(v) =>
                typeof v === "number" ? `${v.toFixed(2)}%` : String(v ?? "")
              }
            />
            <ReferenceLine y={0} stroke={TM_CHART_CSS.gridStrong} />
            {built.worstDate ? (
              <ReferenceLine
                x={built.worstDate}
                stroke={TM_CHART_CSS.negative}
                strokeDasharray="2 4"
                strokeWidth={1}
              />
            ) : null}
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke={TM_CHART_CSS.negative}
              strokeWidth={1.5}
              fill="url(#bt-pane-dd-grad)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
