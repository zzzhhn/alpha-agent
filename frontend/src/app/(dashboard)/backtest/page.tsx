"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { BacktestForm, type BacktestFormParams } from "@/components/backtest/BacktestForm";
import { BacktestKpiStrip } from "@/components/backtest/BacktestKpiStrip";
import { DrawdownChart } from "@/components/backtest/DrawdownChart";
import { MonthlyReturnsHeatmap } from "@/components/backtest/MonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { ZooSaveButton } from "@/components/zoo/ZooSaveButton";
import { runFactorBacktest } from "@/lib/api";
import type { FactorBacktestResponse } from "@/lib/types";

interface PrefillPayload {
  readonly name: string;
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly hypothesis?: string;
}

const PREFILL_KEY = "alphacore.backtest.prefill.v1";

export default function BacktestPage() {
  const { locale } = useLocale();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<FactorBacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<PrefillPayload | null>(null);
  const [lastExpr, setLastExpr] = useState<string>("");
  const [lastName, setLastName] = useState<string>("");

  // P6.D — read /alpha handoff once, then clear so a refresh doesn't
  // re-prefill stale state.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(PREFILL_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(PREFILL_KEY);
      const parsed = JSON.parse(raw) as PrefillPayload;
      if (parsed?.expression) setPrefill(parsed);
    } catch {
      /* malformed — ignore */
    }
  }, []);

  async function run(p: BacktestFormParams) {
    setRunning(true);
    setError(null);
    setLastExpr(p.expression);
    setLastName(prefill?.name ?? "user_factor");
    const res = await runFactorBacktest({
      spec: {
        name: prefill?.name ?? "user_factor",
        hypothesis: prefill?.hypothesis ?? "user-supplied factor",
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
        <h1 className="text-2xl font-semibold text-text">
          {t(locale, "backtest.title")}
        </h1>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
          {t(locale, "backtest.subtitle")}
        </p>
      </header>

      <BacktestForm
        running={running}
        onRun={run}
        initialExpression={prefill?.expression}
        autoRun={Boolean(prefill?.expression)}
      />

      {error && (
        <Card padding="md">
          <p className="text-base text-red">
            {t(locale, "backtest.error")}: {error}
          </p>
        </Card>
      )}

      {result && (
        <>
          <Card padding="md">
            <div className="flex items-center justify-end">
              <ZooSaveButton
                name={lastName}
                expression={lastExpr}
                hypothesis={prefill?.hypothesis}
                headlineMetrics={{
                  testSharpe: result.test_metrics.sharpe,
                  totalReturn:
                    result.equity_curve.length > 0
                      ? result.equity_curve[result.equity_curve.length - 1].value /
                          result.equity_curve[0].value -
                        1
                      : undefined,
                  testIc: result.test_metrics.ic_spearman,
                }}
              />
            </div>
          </Card>
          <BacktestKpiStrip result={result} />
          <Card padding="md">
            <header className="mb-3">
              <h2 className="text-base font-semibold text-text">
                {t(locale, "backtest.equity.title")}
              </h2>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">
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
