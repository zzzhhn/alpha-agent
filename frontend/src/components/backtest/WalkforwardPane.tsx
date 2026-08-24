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
import { TmStatePane } from "@/components/tm/TmStatePane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { WalkForwardWindow } from "@/lib/types";
import type { Run, RunState } from "./types";
import { TM_CHART_CSS } from "@/components/charts";

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
  if (!currentRun) {
    return (
      <TmPane title={title}>
        <TmStatePane
          state="empty"
          title={t(locale, "backtest.evidence.waiting")}
          className="min-h-[220px] rounded-none border-0"
        />
      </TmPane>
    );
  }
  if (folds.length === 0) {
    return (
      <TmPane title={title}>
        <TmStatePane
          state="empty"
          title={t(locale, "backtest.evidence.unavailable")}
          className="min-h-[220px] rounded-none border-0"
        />
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
            <CartesianGrid strokeDasharray="2 4" stroke={TM_CHART_CSS.grid} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: TM_CHART_CSS.muted }}
              interval={0}
              stroke={TM_CHART_CSS.grid}
            />
            <YAxis
              tick={{ fontSize: 10, fill: TM_CHART_CSS.muted }}
              tickFormatter={(v: number) => v.toFixed(2)}
              stroke={TM_CHART_CSS.grid}
              domain={["auto", "auto"]}
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
                typeof v === "number" ? v.toFixed(4) : String(v ?? "")
              }
            />
            <ReferenceLine y={0} stroke={TM_CHART_CSS.gridStrong} />
            <ReferenceLine
              y={IC_THRESHOLD}
              stroke={TM_CHART_CSS.positive}
              strokeDasharray="2 4"
              strokeWidth={1}
              label={{
                value: t(locale, "backtest.evidence.icThreshold"),
                fill: TM_CHART_CSS.muted,
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
                  fill={f.ic >= 0 ? TM_CHART_CSS.positive : TM_CHART_CSS.negative}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
