"use client";

import { useCallback, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { BacktestKpiStrip } from "@/components/backtest/BacktestKpiStrip";
import { DrawdownChart } from "@/components/backtest/DrawdownChart";
import { MonthlyReturnsHeatmap } from "@/components/backtest/MonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { TopBottomTable } from "@/components/signal/TopBottomTable";
import { ExposureChart } from "@/components/signal/ExposureChart";
import {
  runFactorBacktest,
  signalToday,
  signalExposure,
} from "@/lib/api";
import type {
  FactorBacktestResponse,
  SignalSpec,
  SignalTodayResponse,
  ExposureResponse,
} from "@/lib/types";

function extractOps(expr: string): string[] {
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g;
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(expr))) set.add(m[1]);
  return Array.from(set);
}

interface ReportData {
  readonly backtest: FactorBacktestResponse;
  readonly today: SignalTodayResponse;
  readonly exposure: ExposureResponse;
}

export default function ReportPage() {
  const { locale } = useLocale();
  const [factorName, setFactorName] = useState<string>("");
  const [expr, setExpr] = useState<string>("");
  const [intuition, setIntuition] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ReportData | null>(null);

  const generate = useCallback(async (
    name: string, expression: string, hypothesis: string,
  ) => {
    setRunning(true);
    setError(null);
    const spec: SignalSpec = {
      name: name || "factor",
      hypothesis: hypothesis || expression,
      expression,
      operators_used: extractOps(expression),
      lookback: 12,
      universe: "SP500",
      justification: "tear sheet generation",
    };
    const [bt, td, ex] = await Promise.all([
      runFactorBacktest({
        spec, train_ratio: 0.7, direction: "long_only",
        top_pct: 0.30, bottom_pct: 0.30, transaction_cost_bps: 5,
      }),
      signalToday(spec, 10),
      signalExposure(spec, 10),
    ]);
    if (bt.error || td.error || ex.error || !bt.data || !td.data || !ex.data) {
      setError(bt.error ?? td.error ?? ex.error ?? "unknown error");
      setRunning(false);
      return;
    }
    setData({ backtest: bt.data, today: td.data, exposure: ex.data });
    setRunning(false);
  }, []);

  function loadExample(example: FactorExample) {
    setFactorName(example.name);
    setExpr(example.expression);
    setIntuition(locale === "zh" ? example.intuitionZh : example.intuitionEn);
    void generate(
      example.name,
      example.expression,
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
    );
  }

  function runCustom() {
    if (!expr.trim()) return;
    void generate(factorName.trim() || "user_factor", expr.trim(), intuition);
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="report-chrome flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">
            {t(locale, "report.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-muted">
            {t(locale, "report.subtitle")}
          </p>
        </div>
        {data && (
          <Button
            variant="primary"
            size="sm"
            onClick={() => window.print()}
          >
            {t(locale, "report.exportPdf")}
          </Button>
        )}
      </header>

      {/* Factor selector — hidden on print */}
      <Card padding="md" className="report-chrome">
        <header className="mb-3">
          <h2 className="text-sm font-semibold text-text">
            {t(locale, "report.picker.title")}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-muted">
            {t(locale, "report.picker.subtitle")}
          </p>
        </header>

        <div className="mb-3 flex flex-wrap gap-2">
          {FACTOR_EXAMPLES.map((example) => (
            <button
              key={example.name}
              type="button"
              onClick={() => loadExample(example)}
              disabled={running}
              className="rounded-md bg-[var(--toggle-bg)] px-3 py-1.5 text-[11px] text-text hover:bg-accent/15 hover:text-accent disabled:opacity-50"
            >
              {example.name}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          <input
            type="text"
            value={factorName}
            onChange={(e) => setFactorName(e.target.value)}
            placeholder={t(locale, "report.picker.namePlaceholder")}
            className="rounded-md border border-border bg-[var(--toggle-bg)] px-2 py-1.5 text-xs text-text outline-none focus:border-accent"
          />
          <textarea
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            placeholder={t(locale, "report.picker.exprPlaceholder")}
            rows={2}
            className="w-full resize-none rounded-md border border-border bg-[var(--toggle-bg)] p-2 font-mono text-xs text-text outline-none focus:border-accent"
          />
          <div className="flex justify-end">
            <Button onClick={runCustom} disabled={running || expr.trim().length === 0}>
              {running ? t(locale, "report.picker.running") : t(locale, "report.picker.generate")}
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <Card padding="md" className="report-chrome">
          <p className="text-sm text-red">
            {t(locale, "report.error")}: {error}
          </p>
        </Card>
      )}

      {/* Tear sheet — visible on print */}
      {data && (
        <article className="report-tearsheet flex flex-col gap-3">
          <Card padding="md">
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-text">
                  {factorName || data.backtest.factor_name}
                </h2>
                <code className="mt-1 block font-mono text-[11px] text-muted">
                  {expr}
                </code>
              </div>
              <div className="text-right text-[10px] text-muted">
                <div>{t(locale, "report.cover.universe")}: {data.today.universe_size} tickers</div>
                <div>{t(locale, "report.cover.window")}: {data.backtest.equity_curve[0]?.date} → {data.backtest.equity_curve[data.backtest.equity_curve.length - 1]?.date}</div>
                <div>{t(locale, "report.cover.benchmark")}: {data.backtest.benchmark_ticker}</div>
                <div>{t(locale, "report.cover.cost")}: 5 bps</div>
                <div>{t(locale, "report.cover.generated")}: {new Date().toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}</div>
              </div>
            </div>
            {intuition && (
              <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-text/90">
                {intuition}
              </p>
            )}
          </Card>

          <BacktestKpiStrip result={data.backtest} />

          <Card padding="md">
            <header className="mb-2">
              <h3 className="text-sm font-semibold text-text">
                {t(locale, "backtest.equity.title")}
              </h3>
            </header>
            <FactorPnLChart data={data.backtest} height={260} />
          </Card>

          <DrawdownChart equityCurve={data.backtest.equity_curve} />

          {data.backtest.monthly_returns && data.backtest.monthly_returns.length > 0 && (
            <MonthlyReturnsHeatmap data={data.backtest.monthly_returns} />
          )}

          <TopBottomTable today={data.today} loading={false} />
          <ExposureChart data={data.exposure} topN={10} loading={false} />
        </article>
      )}
    </div>
  );
}
