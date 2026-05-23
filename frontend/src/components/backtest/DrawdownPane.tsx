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
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { EquityCurvePoint } from "@/lib/types";
import type { Run, RunState } from "./types";

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

function Skeleton() {
  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="h-3 w-1/3 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-[200px] w-full animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}

function EmptyMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[220px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}

function ErrorPlaceholder({ text }: { readonly text: string }) {
  return (
    <div className="flex h-32 w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
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
        <Skeleton />
      </TmPane>
    );
  }
  if (runState.kind === "error") {
    // Detail lives in <BacktestVerdictBar/>. Panes show a minimal pointer
    // so the same 422 message isn't repeated 3+ times down the page.
    return (
      <TmPane title={title}>
        <ErrorPlaceholder
          text={t(locale, "backtest.evidence.errorPlaceholder")}
        />
      </TmPane>
    );
  }
  if (!currentRun || built.points.length === 0) {
    return (
      <TmPane title={title}>
        <EmptyMessage
          text={
            currentRun
              ? t(locale, "backtest.evidence.unavailable")
              : t(locale, "backtest.evidence.waiting")
          }
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
            {built.worstDate ? (
              <ReferenceLine
                x={built.worstDate}
                stroke="var(--tm-neg)"
                strokeDasharray="2 4"
                strokeWidth={1}
              />
            ) : null}
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke="var(--tm-neg)"
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
