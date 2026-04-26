"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { BacktestForm, type BacktestFormParams } from "@/components/backtest/BacktestForm";
import { BacktestKpiStrip } from "@/components/backtest/BacktestKpiStrip";
import { DrawdownChart } from "@/components/backtest/DrawdownChart";
import { MonthlyReturnsHeatmap } from "@/components/backtest/MonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { runFactorBacktest } from "@/lib/api";
import type { FactorBacktestResponse } from "@/lib/types";

export default function BacktestPage() {
  const { locale } = useLocale();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<FactorBacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(p: BacktestFormParams) {
    setRunning(true);
    setError(null);
    const res = await runFactorBacktest({
      spec: {
        name: "user_factor",
        hypothesis: "user-supplied factor",
        expression: p.expression,
        operators_used: p.operators_used,
        lookback: Math.max(p.lookback, 5),
        universe: "SP500",
        justification: "interactive backtest",
      },
      train_ratio: p.trainRatio,
      direction: p.direction,
      top_pct: p.topPct,
      bottom_pct: p.bottomPct,
      transaction_cost_bps: p.transactionCostBps,
    });
    if (res.error || !res.data) {
      setError(res.error ?? "unknown error");
    } else {
      setResult(res.data);
    }
    setRunning(false);
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header>
        <h1 className="text-xl font-semibold text-text">
          {t(locale, "backtest.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-muted">
          {t(locale, "backtest.subtitle")}
        </p>
      </header>

      <BacktestForm running={running} onRun={run} />

      {error && (
        <Card padding="md">
          <p className="text-sm text-red">
            {t(locale, "backtest.error")}: {error}
          </p>
        </Card>
      )}

      {result && (
        <>
          <BacktestKpiStrip result={result} />
          <Card padding="md">
            <header className="mb-3">
              <h2 className="text-sm font-semibold text-text">
                {t(locale, "backtest.equity.title")}
              </h2>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">
                {t(locale, "backtest.equity.subtitle")}
              </p>
            </header>
            <FactorPnLChart data={result} height={340} />
          </Card>
          <DrawdownChart equityCurve={result.equity_curve} />
          {result.monthly_returns && result.monthly_returns.length > 0 && (
            <MonthlyReturnsHeatmap data={result.monthly_returns} />
          )}
        </>
      )}
    </div>
  );
}
