"use client";

/**
 * TrainTestSplitPane (T6) — equity curve sliced at train_end_index plus
 * OOS-decay KPIs. Chart logic lifted from (dashboard)/backtest/page.tsx
 * (lines 346-443).
 */

import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

export function TrainTestSplitPane({ currentRun }: Props) {
  const { locale } = useLocale();

  if (!currentRun) {
    return (
      <TmPane title="TRAIN/TEST.SPLIT">
        <UnavailableMessage text={t(locale, "backtest.evidence.waiting")} />
      </TmPane>
    );
  }

  const result = currentRun.raw;
  const eq = result.equity_curve;
  const split = result.train_end_index;
  if (!eq || eq.length === 0 || split == null || split <= 0 || split >= eq.length) {
    return (
      <TmPane title="TRAIN/TEST.SPLIT">
        <UnavailableMessage text={t(locale, "backtest.evidence.unavailable")} />
      </TmPane>
    );
  }

  const factorBase = eq[0].value || 1;
  const data = eq.map((p, i) => ({
    date: p.date,
    train: i <= split ? p.value / factorBase : null,
    test: i >= split ? p.value / factorBase : null,
  }));
  const trainSlice = eq.slice(0, split + 1);
  const testSlice = eq.slice(split);
  const trainRet =
    trainSlice.length > 1
      ? trainSlice[trainSlice.length - 1].value / trainSlice[0].value - 1
      : 0;
  const testRet =
    testSlice.length > 1
      ? testSlice[testSlice.length - 1].value / testSlice[0].value - 1
      : 0;
  const trainSharpe = result.train_metrics?.sharpe ?? 0;
  const testSharpe = result.test_metrics?.sharpe ?? 0;
  const oosDecay = result.oos_decay ?? 0;
  const splitDate = eq[split].date;
  const decayTone: "pos" | "neg" | "warn" | "default" =
    oosDecay > 0.5 ? "neg" : oosDecay > 0.2 ? "warn" : oosDecay > 0 ? "default" : "pos";

  return (
    <TmPane
      title="TRAIN/TEST.SPLIT"
      meta={`split @ ${splitDate} · OOS decay ${(oosDecay * 100).toFixed(0)}%`}
    >
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.split.trainSr" as Parameters<typeof t>[1])}
          value={trainSharpe.toFixed(2)}
          tone={trainSharpe > 0 ? "pos" : "neg"}
          sub={t(locale, "backtest.split.inSample" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.split.testSr" as Parameters<typeof t>[1])}
          value={testSharpe.toFixed(2)}
          tone={testSharpe > 0 ? "pos" : "neg"}
          sub={t(locale, "backtest.split.outOfSample" as Parameters<typeof t>[1])}
        />
        <TmKpi
          label={t(locale, "backtest.split.trainRet" as Parameters<typeof t>[1])}
          value={`${(trainRet * 100).toFixed(1)}%`}
          tone={trainRet > 0 ? "pos" : "neg"}
        />
        <TmKpi
          label={t(locale, "backtest.split.testRet" as Parameters<typeof t>[1])}
          value={`${(testRet * 100).toFixed(1)}%`}
          tone={testRet > 0 ? "pos" : "neg"}
        />
        <TmKpi
          label={t(locale, "backtest.split.oosDecay" as Parameters<typeof t>[1])}
          value={`${(oosDecay * 100).toFixed(0)}%`}
          tone={decayTone}
          sub={
            result.overfit_flag
              ? t(locale, "backtest.split.overfit" as Parameters<typeof t>[1])
              : t(locale, "backtest.split.ok" as Parameters<typeof t>[1])
          }
        />
      </TmKpiGrid>
      <div className="h-[220px] w-full px-1 pb-2 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
            <ReferenceLine
              x={splitDate}
              stroke="var(--tm-warn)"
              strokeDasharray="3 3"
              strokeWidth={1.2}
            />
            <Line
              type="monotone"
              dataKey="train"
              name="train"
              stroke="var(--tm-accent)"
              strokeWidth={1.8}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="test"
              name="test"
              stroke="var(--tm-info)"
              strokeWidth={1.8}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

function UnavailableMessage({ text }: { readonly text: string }) {
  return (
    <div className="flex h-[120px] w-full items-center justify-center px-3 text-center font-tm-mono text-[11px] text-tm-muted">
      {text}
    </div>
  );
}
