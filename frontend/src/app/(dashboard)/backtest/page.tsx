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
      mode: p.mode,
      wf_window_days: p.wfWindowDays,
      wf_step_days: p.wfStepDays,
      include_breakdown: p.includeBreakdown,
      mask_earnings_window: p.maskEarningsWindow,
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
          {result.walk_forward && result.walk_forward.length > 0 && (
            <WalkForwardTable windows={result.walk_forward} />
          )}
          {result.daily_breakdown && result.daily_breakdown.length > 0 && (
            <DailyBreakdownPanel breakdown={result.daily_breakdown} factorName={result.factor_name} />
          )}
        </>
      )}
    </div>
  );
}

function DailyBreakdownPanel({
  breakdown, factorName,
}: {
  readonly breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>;
  readonly factorName: string;
}) {
  const { locale } = useLocale();

  // Filter out warm-up days that have no positions (lookback hasn't filled yet)
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  const positiveIc = populated.filter((d) => d.daily_ic > 0).length;
  const hitRate = populated.length > 0 ? positiveIc / populated.length : 0;

  function downloadFlat() {
    // Flatten: one row per (date, side, ticker, weight) so the CSV is
    // load-into-Excel-pivot-friendly. daily_return / daily_ic repeat per row.
    const rows: string[][] = [];
    rows.push(["date", "side", "ticker", "weight", "daily_return", "daily_ic"]);
    for (const d of breakdown) {
      for (const e of d.long_basket) {
        rows.push([d.date, "long", e.ticker, e.weight.toFixed(6), d.daily_return.toFixed(6), d.daily_ic.toFixed(6)]);
      }
      for (const e of d.short_basket) {
        rows.push([d.date, "short", e.ticker, e.weight.toFixed(6), d.daily_return.toFixed(6), d.daily_ic.toFixed(6)]);
      }
    }
    const csv = rows.map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${factorName}_daily_breakdown.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card padding="md">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-text">
            {t(locale, "backtest.breakdown.title")}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">
            {t(locale, "backtest.breakdown.subtitle")
              .replace("{n}", String(populated.length))
              .replace("{hit}", `${(hitRate * 100).toFixed(0)}%`)}
          </p>
        </div>
        <button
          type="button"
          onClick={downloadFlat}
          className="rounded-md border border-border bg-[var(--toggle-bg)] px-3 py-1 text-[13px] text-text hover:bg-accent/15 hover:text-accent"
        >
          {t(locale, "backtest.breakdown.download")}
        </button>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--toggle-bg)]">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "backtest.breakdown.colDate")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.breakdown.colNLong")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.breakdown.colNShort")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.breakdown.colReturn")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.breakdown.colIc")}</th>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "backtest.breakdown.colTopLong")}</th>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "backtest.breakdown.colTopShort")}</th>
            </tr>
          </thead>
          <tbody>
            {populated.slice(-30).reverse().map((d) => (
              <tr key={d.date} className="border-t border-border">
                <td className="px-2 py-1.5 font-mono text-text">{d.date}</td>
                <td className="px-2 py-1.5 text-right font-mono text-muted">{d.long_basket.length}</td>
                <td className="px-2 py-1.5 text-right font-mono text-muted">{d.short_basket.length}</td>
                <td className="px-2 py-1.5 text-right font-mono">
                  <span className={d.daily_return >= 0 ? "text-green" : "text-red"}>
                    {(d.daily_return * 100).toFixed(2)}%
                  </span>
                </td>
                <td className="px-2 py-1.5 text-right font-mono">
                  <span className={d.daily_ic >= 0 ? "text-green" : "text-red"}>
                    {d.daily_ic.toFixed(3)}
                  </span>
                </td>
                <td className="px-2 py-1.5 font-mono text-[12px] text-muted">
                  {d.long_basket.slice(0, 3).map((e) => e.ticker).join(", ")}
                </td>
                <td className="px-2 py-1.5 font-mono text-[12px] text-muted">
                  {d.short_basket.slice(0, 3).map((e) => e.ticker).join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-muted">
        {t(locale, "backtest.breakdown.tableHint")}
      </p>
    </Card>
  );
}

function WalkForwardTable({
  windows,
}: {
  readonly windows: NonNullable<FactorBacktestResponse["walk_forward"]>;
}) {
  const { locale } = useLocale();
  const sharpes = windows.map((w) => w.sharpe);
  const min = Math.min(...sharpes);
  const max = Math.max(...sharpes);

  function spark(value: number): { width: string; color: string } {
    const range = max - min || 1;
    const pct = ((value - min) / range) * 100;
    const color = value > 0 ? "#22c55e" : value < 0 ? "#ef4444" : "#9ca3af";
    return { width: `${Math.max(4, pct)}%`, color };
  }

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "backtest.wf.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
          {t(locale, "backtest.wf.subtitle")}
        </p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="bg-[var(--toggle-bg)]">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium text-muted">{t(locale, "backtest.wf.colWindow")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colSharpe")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colIc")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colReturn")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colMdd")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colTurnover")}</th>
              <th className="px-2 py-1.5 text-right font-medium text-muted">{t(locale, "backtest.wf.colHitRate")}</th>
            </tr>
          </thead>
          <tbody>
            {windows.map((w) => {
              const bar = spark(w.sharpe);
              return (
                <tr key={`${w.window_start}-${w.window_end}`} className="border-t border-border">
                  <td className="px-2 py-1.5 font-mono text-text">
                    {w.window_start} → {w.window_end}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-2 w-12 rounded bg-[var(--toggle-bg)]">
                        <div className="h-full rounded" style={{ width: bar.width, background: bar.color }} />
                      </div>
                      <span className={w.sharpe >= 0 ? "text-text" : "text-red"}>
                        {w.sharpe.toFixed(2)}
                      </span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    <span className={w.ic_spearman >= 0 ? "text-green" : "text-red"}>
                      {w.ic_spearman.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    <span className={w.total_return >= 0 ? "text-green" : "text-red"}>
                      {(w.total_return * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-red">
                    {(w.max_drawdown * 100).toFixed(1)}%
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-muted">
                    {w.turnover.toFixed(2)}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-muted">
                    {(w.hit_rate * 100).toFixed(0)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
