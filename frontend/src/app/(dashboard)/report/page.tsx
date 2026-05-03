"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { BacktestKpiStrip } from "@/components/backtest/BacktestKpiStrip";
import { DrawdownChart } from "@/components/backtest/DrawdownChart";
import { MonthlyReturnsHeatmap } from "@/components/backtest/MonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { CompareEquityChart } from "@/components/charts/CompareEquityChart";
import { TopBottomTable } from "@/components/signal/TopBottomTable";
import { ExposureChart } from "@/components/signal/ExposureChart";
import { listZoo, type ZooEntry } from "@/lib/factor-zoo";
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


interface FactorReport {
  readonly name: string;
  readonly expression: string;
  readonly intuition: string;
  readonly backtest: FactorBacktestResponse;
  readonly today: SignalTodayResponse;
  readonly exposure: ExposureResponse;
}

const REPORT_PREFILL_KEY = "alphacore.report.prefill.v1";

// v4 cross-page parity: instead of hardcoding direction/cost/etc the way
// the legacy fetchAll did (and then having CoverCard advertise "5 bps"
// regardless of what the user set), accept a config and surface it in
// the UI. Defaults match the platform-wide v4 defaults: long_short,
// no neutralize, SPY benchmark, 5 bps cost.
export interface ReportConfig {
  readonly direction: "long_short" | "long_only" | "short_only";
  readonly neutralize: "none" | "sector";
  readonly benchmarkTicker: "SPY" | "RSP";
  readonly transactionCostBps: number;
}

const DEFAULT_REPORT_CONFIG: ReportConfig = {
  direction: "long_short",
  neutralize: "none",
  benchmarkTicker: "SPY",
  transactionCostBps: 5,
};

async function fetchAll(
  name: string, expression: string, hypothesis: string, cfg: ReportConfig,
) {
  const spec: SignalSpec = {
    name: name || "factor",
    hypothesis: hypothesis || expression,
    expression,
    operators_used: [...extractOps(expression)],
    lookback: 12,
    universe: "SP500",
    justification: "tear sheet generation",
  };
  return Promise.all([
    runFactorBacktest({
      spec, train_ratio: 0.7,
      direction: cfg.direction,
      top_pct: 0.30, bottom_pct: 0.30,
      transaction_cost_bps: cfg.transactionCostBps,
      neutralize: cfg.neutralize,
      benchmark_ticker: cfg.benchmarkTicker,
    }),
    signalToday(spec, 10, cfg.neutralize),
    signalExposure(spec, 10, cfg.neutralize),
  ]);
}

export default function ReportPage() {
  const { locale } = useLocale();
  const [factorName, setFactorName] = useState<string>("");
  const [expr, setExpr] = useState<string>("");
  const [intuition, setIntuition] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [primary, setPrimary] = useState<FactorReport | null>(null);
  const [compare, setCompare] = useState<FactorReport | null>(null);
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  const [config, setConfig] = useState<ReportConfig>(DEFAULT_REPORT_CONFIG);

  // Pull zoo entries on mount; refresh when localStorage might have changed
  // (we just track length as a heuristic — full reload happens on focus).
  useEffect(() => {
    setZoo(listZoo());
  }, []);

  // Read /factors zoo handoff (if any) and auto-generate.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(REPORT_PREFILL_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(REPORT_PREFILL_KEY);
      const e = JSON.parse(raw) as ZooEntry;
      if (!e?.expression) return;
      setFactorName(e.name);
      setExpr(e.expression);
      setIntuition(e.intuition ?? "");
      void generate(e.name, e.expression, e.hypothesis ?? "", "primary");
    } catch {
      /* malformed handoff — ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const generate = useCallback(async (
    name: string, expression: string, hypothesis: string,
    slot: "primary" | "compare",
  ) => {
    setRunning(true);
    setError(null);
    const [bt, td, ex] = await fetchAll(name, expression, hypothesis, config);
    if (bt.error || td.error || ex.error || !bt.data || !td.data || !ex.data) {
      setError(bt.error ?? td.error ?? ex.error ?? "unknown error");
      setRunning(false);
      return;
    }
    const built: FactorReport = {
      name, expression,
      intuition: hypothesis,
      backtest: bt.data, today: td.data, exposure: ex.data,
    };
    if (slot === "primary") {
      setPrimary(built);
      setCompare(null);
    } else {
      setCompare(built);
    }
    setRunning(false);
  }, [config]);

  function loadExample(example: FactorExample) {
    setFactorName(example.name);
    setExpr(example.expression);
    const intu = locale === "zh" ? example.intuitionZh : example.intuitionEn;
    setIntuition(intu);
    void generate(
      example.name,
      example.expression,
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
      "primary",
    );
  }

  function loadZooEntry(e: ZooEntry, slot: "primary" | "compare") {
    if (slot === "primary") {
      setFactorName(e.name);
      setExpr(e.expression);
      setIntuition(e.intuition ?? "");
    }
    void generate(e.name, e.expression, e.hypothesis ?? "", slot);
  }

  function runCustom() {
    if (!expr.trim()) return;
    void generate(factorName.trim() || "user_factor", expr.trim(), intuition, "primary");
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <header className="report-chrome flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text">
            {t(locale, "report.title")}
          </h1>
          <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted">
            {t(locale, "report.subtitle")}
          </p>
        </div>
        {primary && (
          <Button
            variant="primary"
            size="sm"
            onClick={() => window.print()}
          >
            {t(locale, "report.exportPdf")}
          </Button>
        )}
      </header>

      <Card padding="md" className="report-chrome">
        <header className="mb-3">
          <h2 className="text-base font-semibold text-text">
            {t(locale, "report.picker.title")}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">
            {t(locale, "report.picker.subtitle")}
          </p>
        </header>

        {/* v4 cross-page parity: tear-sheet config — direction / neutralize /
            benchmark / cost. Used to hardcode long_only + cost=5; that made
            CoverCard advertise parameters the user couldn't see, never mind
            change. Now the UI shows actual settings + lets user adjust. */}
        <div className="mb-3 flex flex-wrap items-center gap-3 text-[13px] text-muted">
          <div className="flex items-center gap-1">
            <span>direction:</span>
            {(["long_short", "long_only", "short_only"] as const).map((d) => (
              <button key={d} type="button" onClick={() => setConfig((c) => ({ ...c, direction: d }))}
                className={`rounded px-2 py-0.5 text-[12px] ${config.direction === d ? "bg-accent text-white" : "bg-[var(--toggle-bg)] hover:text-text"}`}>
                {d}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <span>{t(locale, "backtest.form.neutralize")}:</span>
            {(["none", "sector"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setConfig((c) => ({ ...c, neutralize: m }))}
                className={`rounded px-2 py-0.5 text-[12px] ${config.neutralize === m ? "bg-accent text-white" : "bg-[var(--toggle-bg)] hover:text-text"}`}>
                {t(locale, `backtest.form.neutralize.${m}`)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <span>{t(locale, "backtest.form.benchmark")}:</span>
            {(["SPY", "RSP"] as const).map((bt) => (
              <button key={bt} type="button" onClick={() => setConfig((c) => ({ ...c, benchmarkTicker: bt }))}
                className={`rounded px-2 py-0.5 font-mono text-[12px] ${config.benchmarkTicker === bt ? "bg-accent text-white" : "bg-[var(--toggle-bg)] hover:text-text"}`}>
                {bt}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <span>cost:</span>
            <input type="number" min={0} max={50} step={1} value={config.transactionCostBps}
              onChange={(e) => setConfig((c) => ({ ...c, transactionCostBps: Number(e.target.value) || 0 }))}
              className="w-14 rounded border border-border bg-[var(--toggle-bg)] px-1 text-[12px] text-text" />
            <span className="text-[12px]">bps</span>
          </div>
        </div>

        <div className="mb-3">
          <p className="mb-1 text-[12px] uppercase tracking-wide text-muted">
            {t(locale, "report.picker.fromExamples")}
          </p>
          <div className="flex flex-wrap gap-2">
            {FACTOR_EXAMPLES.map((example) => (
              <button
                key={example.name}
                type="button"
                onClick={() => loadExample(example)}
                disabled={running}
                className="rounded-md bg-[var(--toggle-bg)] px-3 py-1.5 text-[13px] text-text hover:bg-accent/15 hover:text-accent disabled:opacity-50"
              >
                {example.name}
              </button>
            ))}
          </div>
        </div>

        {zoo.length > 0 && (
          <div className="mb-3 border-t border-border pt-3">
            <p className="mb-1 text-[12px] uppercase tracking-wide text-muted">
              {t(locale, "report.picker.fromZoo")}
            </p>
            <div className="flex flex-wrap gap-2">
              {zoo.slice(0, 12).map((z) => (
                <button
                  key={z.id}
                  type="button"
                  onClick={() => loadZooEntry(z, "primary")}
                  disabled={running}
                  className="rounded-md border border-border px-3 py-1.5 text-[13px] text-text hover:bg-accent/15 hover:text-accent disabled:opacity-50"
                  title={z.expression}
                >
                  {z.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <input
            type="text"
            value={factorName}
            onChange={(e) => setFactorName(e.target.value)}
            placeholder={t(locale, "report.picker.namePlaceholder")}
            className="rounded-md border border-border bg-[var(--toggle-bg)] px-2 py-1.5 text-sm text-text outline-none focus:border-accent"
          />
          <textarea
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
            placeholder={t(locale, "report.picker.exprPlaceholder")}
            rows={2}
            className="w-full resize-none rounded-md border border-border bg-[var(--toggle-bg)] p-2 font-mono text-sm text-text outline-none focus:border-accent"
          />
          <div className="flex justify-end">
            <Button onClick={runCustom} disabled={running || expr.trim().length === 0}>
              {running ? t(locale, "report.picker.running") : t(locale, "report.picker.generate")}
            </Button>
          </div>
        </div>

        {primary && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="mb-1 text-[12px] uppercase tracking-wide text-muted">
              {t(locale, "report.picker.compareTitle")}
            </p>
            <p className="mb-2 text-[13px] text-muted">
              {t(locale, "report.picker.compareSubtitle")}
            </p>
            <div className="flex flex-wrap gap-2">
              {FACTOR_EXAMPLES
                .filter((e) => e.expression !== primary.expression)
                .map((example) => (
                  <button
                    key={example.name}
                    type="button"
                    onClick={() =>
                      generate(
                        example.name,
                        example.expression,
                        locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
                        "compare",
                      )
                    }
                    disabled={running}
                    className="rounded-md bg-[var(--toggle-bg)] px-2 py-1 text-[12px] text-muted hover:text-text disabled:opacity-50"
                  >
                    + {example.name}
                  </button>
                ))}
              {zoo
                .filter((z) => z.expression !== primary.expression)
                .slice(0, 6)
                .map((z) => (
                  <button
                    key={z.id}
                    type="button"
                    onClick={() => loadZooEntry(z, "compare")}
                    disabled={running}
                    className="rounded-md border border-border px-2 py-1 text-[12px] text-muted hover:text-text disabled:opacity-50"
                  >
                    + {z.name}
                  </button>
                ))}
              {compare && (
                <Button variant="ghost" size="sm" onClick={() => setCompare(null)}>
                  {t(locale, "report.picker.compareClear")}
                </Button>
              )}
            </div>
          </div>
        )}
      </Card>

      {error && (
        <Card padding="md" className="report-chrome">
          <p className="text-base text-red">
            {t(locale, "report.error")}: {error}
          </p>
        </Card>
      )}

      {primary && compare && (
        <Card padding="md">
          <header className="mb-2">
            <h2 className="text-base font-semibold text-text">
              {t(locale, "report.compare.title")}
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed text-muted">
              {t(locale, "report.compare.subtitle")
                .replace("{a}", primary.name)
                .replace("{b}", compare.name)}
            </p>
          </header>
          <CompareEquityChart
            factor1Name={primary.name}
            factor1={primary.backtest.equity_curve}
            factor2Name={compare.name}
            factor2={compare.backtest.equity_curve}
            benchmark={primary.backtest.benchmark_curve}
            benchmarkTicker={primary.backtest.benchmark_ticker}
          />
        </Card>
      )}

      {primary && (
        <article className="report-tearsheet flex flex-col gap-3">
          <CoverCard r={primary} expr={primary.expression} factorName={primary.name} intuition={primary.intuition} locale={locale} config={config} />
          <BacktestKpiStrip result={primary.backtest} />
          <Card padding="md">
            <header className="mb-2">
              <h3 className="text-base font-semibold text-text">
                {t(locale, "backtest.equity.title")}
              </h3>
            </header>
            <FactorPnLChart data={primary.backtest} height={260} />
          </Card>
          <DrawdownChart equityCurve={primary.backtest.equity_curve} />
          {primary.backtest.monthly_returns && primary.backtest.monthly_returns.length > 0 && (
            <MonthlyReturnsHeatmap data={primary.backtest.monthly_returns} />
          )}
          <TopBottomTable today={primary.today} loading={false} />
          <ExposureChart data={primary.exposure} topN={10} loading={false} />
        </article>
      )}

      {compare && (
        <article className="report-tearsheet flex flex-col gap-3">
          <Card padding="sm">
            <p className="text-[13px] font-semibold uppercase tracking-wide text-muted">
              {t(locale, "report.compare.secondLabel")}
            </p>
          </Card>
          <CoverCard r={compare} expr={compare.expression} factorName={compare.name} intuition={compare.intuition} locale={locale} config={config} />
          <BacktestKpiStrip result={compare.backtest} />
          <DrawdownChart equityCurve={compare.backtest.equity_curve} />
          {compare.backtest.monthly_returns && compare.backtest.monthly_returns.length > 0 && (
            <MonthlyReturnsHeatmap data={compare.backtest.monthly_returns} />
          )}
          <TopBottomTable today={compare.today} loading={false} />
          <ExposureChart data={compare.exposure} topN={10} loading={false} />
        </article>
      )}
    </div>
  );
}

function CoverCard({
  r, expr, factorName, intuition, locale, config,
}: {
  r: FactorReport;
  expr: string;
  factorName: string;
  intuition: string;
  locale: "zh" | "en";
  config: ReportConfig;
}) {
  return (
    <Card padding="md">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">
            {factorName || r.backtest.factor_name}
          </h2>
          <code className="mt-1 block font-mono text-[13px] text-muted">{expr}</code>
        </div>
        <div className="text-right text-[12px] text-muted">
          <div>{t(locale, "report.cover.universe")}: {r.today.universe_size} tickers</div>
          <div>{t(locale, "report.cover.window")}: {r.backtest.equity_curve[0]?.date} → {r.backtest.equity_curve[r.backtest.equity_curve.length - 1]?.date}</div>
          <div>{t(locale, "report.cover.benchmark")}: {r.backtest.benchmark_ticker}</div>
          <div>direction: {config.direction}{config.neutralize === "sector" ? " · sector-neutral" : ""}</div>
          <div>{t(locale, "report.cover.cost")}: {config.transactionCostBps} bps</div>
          <div>{t(locale, "report.cover.generated")}: {new Date().toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}</div>
        </div>
      </div>
      {intuition && (
        <p className="mt-3 border-t border-border pt-3 text-[13px] leading-relaxed text-text/90">
          {intuition}
        </p>
      )}
    </Card>
  );
}
