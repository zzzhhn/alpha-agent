"use client";

/**
 * WalkforwardPane — default evidence pane #3 for /backtest redesign (T5).
 *
 * 4-state lifecycle: waiting / loading / ok / error.
 * Reads `currentRun.raw.walk_forward` (optional in FactorBacktestResponse —
 * only populated when the request used `mode: "walk_forward"`).
 *
 * Renders a BarChart of per-window IC (Spearman). Threshold line at
 * IC=0.02 highlights the conventional "non-noise" floor.
 */

import { useMemo } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { WalkForwardWindow } from "@/lib/types";
import type { Run, RunState } from "./types";

interface Props {
  readonly runState: RunState;
  readonly currentRun: Run | null;
}

interface FoldPoint {
  readonly label: string;
  readonly ic: number;
}

function buildFolds(windows: readonly WalkForwardWindow[]): FoldPoint[] {
  return windows.map((w, idx) => ({
    label: `${idx + 1}: ${w.window_start.slice(2, 10)}`,
    ic: w.ic_spearman,
  }));
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

const IC_THRESHOLD = 0.02;

export function WalkforwardPane({ runState, currentRun }: Props) {
  const { locale } = useLocale();
  const title = t(locale, "backtest.evidence.walkforward");

  const windows = currentRun?.raw.walk_forward ?? null;
  const folds = useMemo<FoldPoint[]>(
    () => (windows && windows.length > 0 ? buildFolds(windows) : []),
    [windows],
  );

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
  if (!currentRun) {
    return (
      <TmPane title={title}>
        <EmptyMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }
  if (folds.length === 0) {
    return (
      <TmPane title={title}>
        <EmptyMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const metaText = t(locale, "backtest.evidence.foldsCount").replace(
    "{n}",
    String(folds.length),
  );

  return (
    <TmPane
      title={title}
      meta={`${metaText} · ${t(locale, "backtest.evidence.icThreshold")}`}
    >
      <div className="w-full px-1 pb-2 pt-2" style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={folds}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              interval={0}
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
                typeof v === "number" ? v.toFixed(4) : String(v ?? "")
              }
            />
            <ReferenceLine y={0} stroke="var(--tm-rule-2)" />
            <ReferenceLine
              y={IC_THRESHOLD}
              stroke="var(--tm-accent)"
              strokeDasharray="2 4"
              strokeWidth={1}
              label={{
                value: t(locale, "backtest.evidence.icThreshold"),
                fill: "var(--tm-muted)",
                fontSize: 10,
                fontFamily: "var(--font-jetbrains-mono)",
                position: "insideTopRight",
              }}
            />
            <Bar
              dataKey="ic"
              name={t(locale, "backtest.evidence.foldIc")}
              isAnimationActive={false}
            >
              {folds.map((f, idx) => (
                <Cell
                  key={`fold-${idx}`}
                  fill={f.ic >= 0 ? "var(--tm-pos)" : "var(--tm-neg)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
