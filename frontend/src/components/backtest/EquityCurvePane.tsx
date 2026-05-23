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
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { EquityCurvePoint } from "@/lib/types";
import type { Run, RunState } from "./types";

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
  if (!currentRun || data.length === 0) {
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

  const last = data[data.length - 1];
  const factorPct = ((last.factor - 1) * 100).toFixed(1);
  const benchPct = ((last.benchmark - 1) * 100).toFixed(1);

  return (
    <TmPane title={title} meta={`factor ${factorPct}% · bench ${benchPct}%`}>
      <div className="w-full px-1 pb-2 pt-2" style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
              tickFormatter={(v: number) => v.toFixed(2)}
              stroke="var(--tm-rule)"
              domain={["auto", "auto"]}
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
                typeof v === "number" ? v.toFixed(3) : String(v ?? "")
              }
            />
            <Legend
              wrapperStyle={{
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
              }}
            />
            <ReferenceLine y={1} stroke="var(--tm-rule-2)" strokeWidth={1} />
            <Line
              type="monotone"
              dataKey="benchmark"
              name={t(locale, "backtest.evidence.benchmark")}
              stroke="var(--tm-muted)"
              strokeWidth={1.5}
              dot={false}
              strokeDasharray="3 3"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="factor"
              name={t(locale, "backtest.evidence.factor")}
              stroke="var(--tm-accent)"
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
