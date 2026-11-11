"use client";

/** Report composer → current-run verdict and equity → optional comparison / diagnostics. */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton, TmDisclosureButton } from "@/components/tm/TmButton";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { ReportComposer, ReportEvidenceEmpty, reportDirectionLabel, isReportDraftDirty, type ReportConfig } from "@/components/report/ReportComposer";
import { researchNumberError } from "@/lib/research-input-validation";
import { ReportVerdictHero } from "@/components/report/ReportVerdictHero";
import { ReportCompareBar } from "@/components/report/ReportCompareBar";
import { ReportDeepModal } from "@/components/report/ReportDeepModal";
import { TmBacktestKpiStrip } from "@/components/backtest/TmBacktestKpiStrip";
import { TmDrawdownChart } from "@/components/backtest/TmDrawdownChart";
import { TmMonthlyReturnsHeatmap } from "@/components/backtest/TmMonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { TmCompareEquityChart } from "@/components/charts/TmCompareEquityChart";
import { TmTopBottomTable } from "@/components/signal/TmTopBottomTable";
import { TmExposureChart } from "@/components/signal/TmExposureChart";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
// IC timeseries, folded in from the merged /signal page (/signal redirects here).
import { TmICTimeseriesChart } from "@/components/signal/TmICTimeseriesChart";
import { listZoo, seedZooIfFirstRun, type ZooEntry } from "@/lib/factor-zoo";
import {
  dailyReturns,
  sortinoRatio,
  calmarRatio,
  activeReturns,
  trackingError,
  informationRatio,
  skewness,
  excessKurtosis,
  valueAtRisk,
  conditionalVaR,
  maxLossStreak,
  maxWinStreak,
  pearsonCorr,
  rollingCorr,
  yearlyStats,
  periodReturn,
  recoveryStats,
  jaccard,
  intersection,
  type YearStats,
} from "@/lib/report-metrics";
import {
  runFactorBacktest,
  signalToday,
  signalExposure,
  signalIcTimeseries,
} from "@/lib/api";
import type {
  FactorBacktestResponse,
  SignalSpec,
  SignalTodayResponse,
  ExposureResponse,
  ICTimeseriesResponse,
} from "@/lib/types";

interface FactorReport {
  readonly name: string;
  readonly expression: string;
  readonly intuition: string;
  readonly backtest: FactorBacktestResponse;
  readonly today: SignalTodayResponse;
  readonly exposure: ExposureResponse;
  readonly icTs: ICTimeseriesResponse;
  readonly config: ReportConfig;
  readonly generatedAt: string;
}

const REPORT_PREFILL_KEY = "alphacore.report.prefill.v1";

// #4c: persist the user's DIRECTION choice across runs. Only the direction
// is persisted (neutralize / benchmark / cost stay per-session, and an
// example load overrides direction with its proven config for that run).
const REPORT_DIRECTION_KEY = "alphacore.report.direction.v1";
type ReportDirection = "long_short" | "long_only" | "short_only";

function readPersistedDirection(): ReportDirection | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(REPORT_DIRECTION_KEY);
    if (raw === "long_short" || raw === "long_only" || raw === "short_only") {
      return raw;
    }
  } catch {
    /* storage blocked — fall back to default */
  }
  return null;
}

function persistDirection(dir: ReportDirection): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(REPORT_DIRECTION_KEY, dir);
  } catch {
    /* storage blocked — non-fatal */
  }
}

export type { ReportConfig } from "@/components/report/ReportComposer";

const DEFAULT_REPORT_CONFIG: ReportConfig = {
  direction: "long_short",
  neutralize: "none",
  benchmarkTicker: "SPY",
  // Same default as Backtest and Alpha (10 bps per side). Only new drafts use
  // this; a loaded/saved report keeps the cost it was generated with.
  transactionCostBps: 10,
};

// Backend FactorSpec.hypothesis is bounded to 200 chars (Pydantic
// max_length=200). UI display strings (intuitionZh, hypothesisZh on
// some v3 examples, free-form user input) can blow past that.
// Truncating at the boundary so no caller can break the contract.
const MAX_HYPOTHESIS_CHARS = 200;
function clipHypothesis(s: string): string {
  if (s.length <= MAX_HYPOTHESIS_CHARS) return s;
  // Reserve 1 char for the ellipsis so backend gets exactly 200.
  return s.slice(0, MAX_HYPOTHESIS_CHARS - 1) + "…";
}

async function fetchAll(
  name: string,
  expression: string,
  hypothesis: string,
  cfg: ReportConfig,
) {
  const spec: SignalSpec = {
    name: name || "factor",
    hypothesis: clipHypothesis(hypothesis || expression),
    expression,
    operators_used: [...extractOps(expression)],
    lookback: 12,
    universe: "SP500",
    justification: "tear sheet generation",
  };
  return Promise.all([
    runFactorBacktest({
      spec,
      train_ratio: 0.7,
      direction: cfg.direction,
      top_pct: 0.30,
      bottom_pct: 0.30,
      transaction_cost_bps: cfg.transactionCostBps,
      neutralize: cfg.neutralize,
      benchmark_ticker: cfg.benchmarkTicker,
    }),
    signalToday(spec, 10, cfg.neutralize),
    signalExposure(spec, 10, cfg.neutralize),
    // IC timeseries folded in from the merged /signal page (252d window).
    signalIcTimeseries(spec, 252, cfg.neutralize),
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
  // #4c: seed direction from localStorage (lazy init) so the user's last
  // choice is reused on the next run. SSR-safe: readPersistedDirection
  // returns null on the server, falling back to the default.
  const [config, setConfig] = useState<ReportConfig>(() => ({
    ...DEFAULT_REPORT_CONFIG,
    direction: readPersistedDirection() ?? DEFAULT_REPORT_CONFIG.direction,
  }));
  // #4d: name of the example staged (loaded but not yet run). Highlights
  // its row in the list and the Run button; cleared once a report runs or
  // the user edits the expression by hand.
  const [stagedName, setStagedName] = useState<string | null>(null);
  const [stagedZoo, setStagedZoo] = useState<ZooEntry | null>(null);
  // R3: the long-tail tear-sheet sections collapse into a floating-button modal.
  const [deepOpen, setDeepOpen] = useState(false);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [compareDetailsOpen, setCompareDetailsOpen] = useState(false);

  useEffect(() => {
    seedZooIfFirstRun();
    setZoo(listZoo());
    // Client-only: re-sync direction from storage in case lazy init ran
    // before hydration with a server default.
    const stored = readPersistedDirection();
    if (stored) setConfig((c) => ({ ...c, direction: stored }));
  }, []);

  // #4c: persist DIRECTION whenever it changes.
  useEffect(() => {
    persistDirection(config.direction);
  }, [config.direction]);

  // generate accepts hypothesis (short, ≤200 chars, sent to backend)
  // and an optional intuitionForCover (display-only, can be longer).
  // The split avoids the bug where intuitionZh (~220 chars on v3 picks)
  // leaked into the backend hypothesis field and triggered HTTP 422.
  const generate = useCallback(
    async (
      name: string,
      expression: string,
      hypothesis: string,
      slot: "primary" | "compare",
      intuitionForCover?: string,
      requestedConfig: ReportConfig = config,
    ) => {
      const costError = researchNumberError("transactionCostBps", requestedConfig.transactionCostBps, locale);
      if (costError) { setError(costError); return; }
      setRunning(true);
      setError(null);
      try {
        const [bt, td, ex, ic] = await fetchAll(name, expression, hypothesis, requestedConfig);
        if (bt.error || td.error || ex.error || ic.error || !bt.data || !td.data || !ex.data || !ic.data) {
          setError(bt.error ?? td.error ?? ex.error ?? ic.error ?? "Missing report evidence");
          return;
        }
        const built: FactorReport = {
          name, expression, intuition: intuitionForCover ?? hypothesis,
          backtest: bt.data, today: td.data, exposure: ex.data, icTs: ic.data,
          config: { ...requestedConfig }, generatedAt: new Date().toISOString(),
        };
        if (slot === "primary") {
          setPrimary(built);
          setCompare(null);
          setStagedName(null);
        } else {
          setCompare(built);
          setComparisonOpen(true);
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      } finally {
        setRunning(false);
      }
    },
    [config, locale],
  );

  // P6.D — read /factors zoo handoff (if any) and auto-generate.
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
      void generate(
        e.name,
        e.expression,
        e.hypothesis ?? "",
        "primary",
        e.intuition ?? e.hypothesis ?? "",
      );
    } catch {
      /* malformed handoff — ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Source selection loads a draft; only Generate computes evidence.
  // Preserve the existing fixed 30% sleeves, not the fixtures' historical returns.
  const [stagedExample, setStagedExample] = useState<FactorExample | null>(null);

  function stageExample(example: FactorExample) {
    setFactorName(example.name);
    setExpr(example.expression);
    setIntuition(locale === "zh" ? example.hypothesisZh : example.hypothesisEn);
    // Preserve this route's established direction / neutralization / benchmark wiring.
    setConfig((c) => ({
      direction: example.direction ?? c.direction,
      neutralize: example.neutralize ?? c.neutralize,
      benchmarkTicker: example.benchmarkTicker ?? c.benchmarkTicker,
      transactionCostBps: example.transactionCostBps ?? c.transactionCostBps,
    }));
    setStagedExample(example);
    setStagedZoo(null);
    setStagedName(example.name);
  }

  // The source hypothesis is context, not a copied historical performance verdict.
  function runStaged() {
    const example = stagedExample;
    if (!example) return;
    void generate(
      example.name,
      example.expression,
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
      "primary",
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
    );
  }

  function stageZooEntry(entry: ZooEntry) {
    setFactorName(entry.name);
    setExpr(entry.expression);
    setIntuition(entry.intuition ?? entry.hypothesis ?? "");
    setStagedExample(null);
    setStagedZoo(entry);
    setStagedName(entry.name);
  }

  function loadZooEntry(e: ZooEntry, slot: "primary" | "compare") {
    if (slot === "primary") {
      setFactorName(e.name);
      setExpr(e.expression);
      setIntuition(e.intuition ?? "");
    }
    void generate(
      e.name,
      e.expression,
      e.hypothesis ?? "",
      slot,
      e.intuition ?? e.hypothesis ?? "",
      slot === "compare" && primary ? primary.config : config,
    );
  }

  function runCustom() {
    if (!expr.trim()) return;
    // intuition is the long human-readable display field; do NOT pass
    // it as backend hypothesis (Pydantic 200-char cap). For custom user
    // input we synthesize a short hypothesis but pass the user's full
    // intuition through as the cover-display field. clipHypothesis at
    // fetchAll guards anyway.
    const name = factorName.trim() || "user_factor";
    void generate(
      name,
      expr.trim(),
      stagedZoo?.hypothesis || `tearsheet for ${name}`,
      "primary",
      intuition,
    );
  }

  const draftDirty = isReportDraftDirty(factorName, expr, config, primary);

  return (
    <TmScreen>
      <WorkbenchHeader
        eyebrow={locale === "zh" ? "研究 · 证据报告" : "Research · Evidence report"}
        title={locale === "zh" ? "报告" : "Report"}
        subtitle={locale === "zh" ? "把回测、风险和信号证据汇总为可复核的研究结论。" : "Consolidate backtest, risk, and signal evidence into a reviewable conclusion."}
        statuses={[
          { label: locale === "zh" ? "主因子" : "Primary", value: primary?.name || factorName || "—" },
          { label: locale === "zh" ? "生成状态" : "Generation", value: running ? (locale === "zh" ? "运行中" : "RUNNING") : error ? (locale === "zh" ? "失败" : "ERROR") : draftDirty ? (locale === "zh" ? "草稿未验证" : "DRAFT NOT RUN") : primary ? (locale === "zh" ? "已完成" : "READY") : (locale === "zh" ? "待配置" : "IDLE"), tone: error ? "negative" : running || draftDirty ? "warning" : primary ? "positive" : "default" },
          { label: locale === "zh" ? "对比因子" : "Comparison", value: compare?.name ?? "—" },
        ]}
      />
      {primary && <TmSubbar className="report-chrome">
        <TmSubbarKV
          label={locale === "zh" ? "当前报告" : "Current report"}
          value={primary.name}
        />
        {primary && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label={locale === "zh" ? "标的数" : "Universe"}
              value={`${primary.today.universe_size}`}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label={locale === "zh" ? "样本外夏普" : "OOS Sharpe"}
              value={primary.backtest.test_metrics.sharpe.toFixed(2)}
            />
          </>
        )}
        {compare && (
          <>
            <TmSubbarSep />
            <TmSubbarKV label={locale === "zh" ? "对比" : "Compare"} value={compare.name} />
          </>
        )}
        <TmSubbarSpacer />
        {primary?.backtest.overfit_flag && (
          <TmStatusPill tone="err">
            {locale === "zh" ? "过拟合 · 样本外衰减" : "Overfit · OOS decay"}{" "}
            {((primary.backtest.oos_decay ?? 0) * 100).toFixed(0)}%
          </TmStatusPill>
        )}
        {primary && (
          <TmStatusPill
            tone={primary.backtest.survivorship_corrected ? "ok" : "warn"}
          >
            {primary.backtest.survivorship_corrected
              ? `SP500-AS-OF · ${primary.backtest.membership_as_of ?? "—"}`
              : locale === "zh" ? "旧版成分股口径" : "Legacy membership"}
          </TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">{locale === "zh" ? "计算中 · 保留上次报告" : "Running · previous report retained"}</TmStatusPill>}
        {error && <TmStatusPill tone="err">{locale === "zh" ? "本次失败 · 保留上次报告" : "Run failed · previous report retained"}</TmStatusPill>}
        {primary && (
          <TmButton
            variant="ghost"
            onClick={() => window.print()}
            className="-my-1 px-2"
          >
            {t(locale, "report.exportPdf")}
          </TmButton>
        )}
        {primary && (
          <TmButton
            variant="ghost"
            onClick={async () => {
              // B6 (2026-05-19): self-contained HTML tearsheet download.
              // Export the displayed report's immutable inputs, not a new draft.
              // streamed HTML body, trigger browser save dialog. Works
              // offline once the user has Chart.js cached.
              const res = await fetch(
                `/api/v1/factor/backtest/export?factor_name=${encodeURIComponent(primary.name)}&lang=${locale}`,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  credentials: "include",
                  body: JSON.stringify({
                    spec: {
                      name: primary.name,
                      hypothesis: primary.name,
                      expression: primary.expression,
                      operators_used: [...extractOps(primary.expression)],
                      lookback: 12,
                      universe: "SP500",
                      justification: "tearsheet export",
                    },
                    direction: primary.config.direction,
                    train_ratio: 0.7,
                    top_pct: 0.30,
                    bottom_pct: 0.30,
                    transaction_cost_bps: primary.config.transactionCostBps,
                    neutralize: primary.config.neutralize,
                    benchmark_ticker: primary.config.benchmarkTicker,
                    include_breakdown: false,
                  }),
                },
              );
              if (!res.ok) {
                alert(`Export failed: HTTP ${res.status}`);
                return;
              }
              const blob = await res.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `${primary.name}_tearsheet.html`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="-my-1 px-2"
          >
            {locale === "zh" ? "下载 HTML" : "Export HTML"}
          </TmButton>
        )}
      </TmSubbar>}

      <ReportComposer
        factorName={factorName}
        onFactorName={(v) => {
          setFactorName(v);
          // Hand-editing the name detaches from the staged example.
          setStagedExample(null);
          setStagedZoo(null);
          setStagedName(null);
        }}
        expr={expr}
        onExpr={(v) => {
          setExpr(v);
          // Hand-editing the expression detaches from the staged example.
          setStagedExample(null);
          setStagedZoo(null);
          setStagedName(null);
          setIntuition("");
        }}
        config={config}
        onConfig={setConfig}
        zoo={zoo}
        running={running}
        sourceName={stagedName}
        onExample={stageExample}
        onZoo={stageZooEntry}
        onGenerate={stagedExample ? runStaged : runCustom}
      />

      {draftDirty && <p role="status" className="report-chrome border-l-[3px] border-l-tm-warn bg-tm-bg-2 px-4 py-2 font-tm-mono text-xs leading-5 text-tm-warn">{locale === "zh" ? "草稿已改动，尚未验证。下方结论、图表与导出仍对应上次完成的报告；生成新报告后才会更新。" : "Draft changed and has not been evaluated. The verdict, charts and exports below still belong to the previous completed report until you generate again."}</p>}

      {error && (
        <TmPane title={locale === "zh" ? "报告生成失败" : "Report generation failed"} meta={locale === "zh" ? "输入与已有报告已保留" : "Inputs and previous evidence retained"}>
          <p role="alert" className="px-4 py-3 font-tm-mono text-xs text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      {primary && <ReportVerdictHero primary={primary} running={running} />}

      {!primary && <ReportEvidenceEmpty running={running} failed={Boolean(error)} hasDraft={Boolean(expr.trim())} />}

      {primary && (
        <article className="report-tearsheet flex min-w-0 flex-col">
          <div className="grid min-w-0 grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)]">
            <TmPane title="EQUITY.CURVE" meta={primary.backtest.equity_curve.length + (locale === "zh" ? " 个交易日 · " : " sessions · ") + primary.backtest.benchmark_ticker} className="lg:border-r lg:border-tm-rule">
              <div className="px-3 py-3"><FactorPnLChart data={primary.backtest} height={280} /></div>
            </TmPane>
            <ReportCoverPane r={primary} expr={primary.expression} factorName={primary.name} intuition={primary.intuition} config={primary.config} />
          </div>
          <TmBacktestKpiStrip result={primary.backtest} />
          <ReportDeepModal open={deepOpen} onOpen={() => setDeepOpen(true)} onClose={() => setDeepOpen(false)}>
            <RiskMetricsPane report={primary} />
            <TailRiskPane report={primary} />
            <RecentMomentumPane report={primary} />
            <TmDrawdownChart equityCurve={primary.backtest.equity_curve} />
            <RecoveryStatsPane equityCurve={primary.backtest.equity_curve} />
            <YearlyBreakdownPane equityCurve={primary.backtest.equity_curve} />
            {primary.backtest.monthly_returns && primary.backtest.monthly_returns.length > 0 && <TmMonthlyReturnsHeatmap data={primary.backtest.monthly_returns} />}
            <TmTopBottomTable today={primary.today} loading={false} />
            <TmICTimeseriesChart data={primary.icTs} loading={false} />
            <TmExposureChart data={primary.exposure} topN={10} loading={false} />
          </ReportDeepModal>
        </article>
      )}

      {primary && <div className="min-w-0">
        <TmDisclosureButton expanded={comparisonOpen} onClick={() => setComparisonOpen((open) => !open)} label={locale === "zh" ? "因子对比" : "Factor comparison"} meta={compare ? primary.name + " / " + compare.name : locale === "zh" ? "可选 · 单独计算第二个因子" : "Optional · computes a second factor"} className="report-chrome" aria-controls="report-comparison" />
        <section id="report-comparison" className={comparisonOpen ? "min-w-0" : "hidden print:block"}>
          <ReportCompareBar zoo={zoo} examples={FACTOR_EXAMPLES} primaryExpression={primary.expression} compareName={compare?.name ?? null} onCompare={(entry) => loadZooEntry(entry, "compare")} onCompareExample={(example) => void generate(example.name, example.expression, locale === "zh" ? example.hypothesisZh : example.hypothesisEn, "compare", locale === "zh" ? example.hypothesisZh : example.hypothesisEn, primary.config)} onClear={() => setCompare(null)} running={running} />
          {compare && <>
            <TmPane title="COMPARE.OVERLAY" meta={primary.name + " / " + compare.name + " · " + primary.backtest.benchmark_ticker}>
              <TmCompareEquityChart factor1Name={primary.name} factor1={primary.backtest.equity_curve} factor2Name={compare.name} factor2={compare.backtest.equity_curve} benchmark={primary.backtest.benchmark_curve} benchmarkTicker={primary.backtest.benchmark_ticker} />
            </TmPane>
            <CompareMetricsPane primary={primary} compare={compare} />
            <TmDisclosureButton expanded={compareDetailsOpen} onClick={() => setCompareDetailsOpen((open) => !open)} label={locale === "zh" ? "相关性、持仓重叠与第二份报告" : "Correlation, holdings overlap and second report"} className="report-chrome" aria-controls="report-comparison-details" />
            <div id="report-comparison-details" className={compareDetailsOpen ? "min-w-0" : "hidden print:block"}>
              <CompareCorrelationPane primary={primary} compare={compare} />
              <TickerOverlapPane primary={primary} compare={compare} />
              <article className="report-tearsheet flex min-w-0 flex-col">
                <ReportCoverPane r={compare} expr={compare.expression} factorName={compare.name} intuition={compare.intuition} config={compare.config} />
                <TmBacktestKpiStrip result={compare.backtest} />
                <TmDrawdownChart equityCurve={compare.backtest.equity_curve} />
                {compare.backtest.monthly_returns && compare.backtest.monthly_returns.length > 0 && <TmMonthlyReturnsHeatmap data={compare.backtest.monthly_returns} />}
                <TmTopBottomTable today={compare.today} loading={false} />
                <TmICTimeseriesChart data={compare.icTs} loading={false} />
                <TmExposureChart data={compare.exposure} topN={10} loading={false} />
              </article>
            </div>
          </>}
        </section>
      </div>}
    </TmScreen>
  );
}

/* ── REPORT.COVER pane (per slot) ─────────────────────────────────── */

function ReportCoverPane({
  r,
  expr,
  factorName,
  intuition,
  config,
}: {
  readonly r: FactorReport;
  readonly expr: string;
  readonly factorName: string;
  readonly intuition: string;
  readonly config: ReportConfig;
}) {
  const { locale } = useLocale();
  const eq = r.backtest.equity_curve;
  const startDate = eq[0]?.date ?? "—";
  const endDate = eq[eq.length - 1]?.date ?? "—";
  const zh = locale === "zh";
  const [hypothesisOpen, setHypothesisOpen] = useState(false);
  const rows = [
    { label: zh ? "样本区间" : "Sample window", value: startDate + " → " + endDate },
    { label: zh ? "研究范围" : "Universe", value: "S&P 500 · " + r.today.universe_size + (zh ? " 个标的" : " tickers") },
    { label: zh ? "方向 / 中性化" : "Direction / neutralization", value: reportDirectionLabel(config.direction, locale) + " / " + (config.neutralize === "sector" ? (zh ? "行业中性" : "Sector neutral") : (zh ? "不中性化" : "None")) },
    { label: zh ? "基准 / 成本" : "Benchmark / cost", value: r.backtest.benchmark_ticker + " / " + config.transactionCostBps + " bps" },
  ];
  return (
    <TmPane title={zh ? "报告依据" : "Report basis"} meta={zh ? "生成时参数" : "Run settings"}>
      <div className="p-4">
        <h2 className="font-tm-mono text-sm font-semibold text-tm-fg">{factorName || r.backtest.factor_name}</h2>
        <code className="mt-2 block break-all font-tm-mono text-xs leading-5 text-tm-fg-2">{expr}</code>
        <dl className="mt-3 font-tm-mono text-xs">{rows.map(({ label, value }) => <div key={label} className="flex flex-wrap justify-between gap-x-3 gap-y-1 border-t border-tm-rule py-2"><dt className="text-tm-muted">{label}</dt><dd className="text-tm-fg-2">{value}</dd></div>)}</dl>
        {intuition && <div className="mt-2"><TmDisclosureButton expanded={hypothesisOpen} onClick={() => setHypothesisOpen((open) => !open)} label={zh ? "来源假设（非本次结果）" : "Source hypothesis (not run evidence)"} className="report-chrome" /><p className={(hypothesisOpen ? "" : "hidden print:block ") + "pt-2 font-tm-mono text-xs leading-5 text-tm-fg-2"}>{intuition}</p></div>}
        <p className="mt-3 border-t border-tm-rule pt-2 font-tm-mono text-xs text-tm-muted">{t(locale, "report.cover.generated")}: {new Date(r.generatedAt).toLocaleString(zh ? "zh-CN" : "en-US")}</p>
      </div>
    </TmPane>
  );
}

/* ── v3 #1 — RISK.METRICS pane ────────────────────────────────────── */

function RiskMetricsPane({ report }: { readonly report: FactorReport }) {
  const { locale } = useLocale();
  const eq = report.backtest.equity_curve;
  const bench = report.backtest.benchmark_curve;
  const m = useMemo(() => {
    const rets = dailyReturns(eq);
    const active = activeReturns(eq, bench);
    return {
      sortino: sortinoRatio(rets),
      calmar: calmarRatio(eq),
      ir: informationRatio(active),
      te: trackingError(active),
      skew: skewness(rets),
      kurt: excessKurtosis(rets),
    };
  }, [eq, bench]);
  return (
    <TmPane title="RISK.METRICS" meta="institutional risk-adjusted ratios">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.risk.desc")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label="SORTINO"
          value={m.sortino.toFixed(2)}
          tone={m.sortino > 1 ? "pos" : m.sortino < 0 ? "neg" : "default"}
          sub="downside-only Sharpe"
        />
        <TmKpi
          label="CALMAR"
          value={m.calmar.toFixed(2)}
          tone={m.calmar > 1 ? "pos" : m.calmar < 0 ? "neg" : "default"}
          sub="ann. ret / |maxDD|"
        />
        <TmKpi
          label="IR"
          value={m.ir.toFixed(2)}
          tone={m.ir > 0 ? "pos" : "neg"}
          sub="active / TE"
        />
        <TmKpi
          label="TE"
          value={`${(m.te * 100).toFixed(1)}%`}
          sub="ann. tracking error"
        />
        <TmKpi
          label="SKEW"
          value={m.skew.toFixed(2)}
          tone={m.skew > 0 ? "pos" : "neg"}
          sub={m.skew > 0 ? "right-tailed" : "left-tailed"}
        />
        <TmKpi
          label="EXC. KURT"
          value={m.kurt.toFixed(2)}
          tone={m.kurt > 1 ? "warn" : "default"}
          sub={m.kurt > 1 ? "fat tails" : "near-normal"}
        />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── v3 #2 — TAIL.RISK pane ───────────────────────────────────────── */

function TailRiskPane({ report }: { readonly report: FactorReport }) {
  const { locale } = useLocale();
  const eq = report.backtest.equity_curve;
  const m = useMemo(() => {
    const rets = dailyReturns(eq);
    const wins = rets.filter((r) => r > 0);
    const losses = rets.filter((r) => r < 0);
    const sumGains = wins.reduce((a, b) => a + b, 0);
    const sumLosses = losses.reduce((a, b) => a + b, 0);
    return {
      var5: valueAtRisk(rets, 0.05),
      var1: valueAtRisk(rets, 0.01),
      cvar5: conditionalVaR(rets, 0.05),
      maxLoss: maxLossStreak(rets),
      maxWin: maxWinStreak(rets),
      profitFactor: sumLosses < 0 ? Math.abs(sumGains / sumLosses) : 0,
    };
  }, [eq]);
  return (
    <TmPane title="TAIL.RISK" meta="historical VaR / streak / profit factor">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.tail.desc")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label="VAR 5%"
          value={`${(m.var5 * 100).toFixed(2)}%`}
          tone="neg"
          sub="5th percentile day"
        />
        <TmKpi
          label="VAR 1%"
          value={`${(m.var1 * 100).toFixed(2)}%`}
          tone="neg"
          sub="1st percentile day"
        />
        <TmKpi
          label="CVAR 5%"
          value={`${(m.cvar5 * 100).toFixed(2)}%`}
          tone="neg"
          sub="mean worst 5% days"
        />
        <TmKpi
          label="MAX LOSS RUN"
          value={`${m.maxLoss}d`}
          tone={m.maxLoss > 5 ? "warn" : "default"}
          sub="consecutive negative"
        />
        <TmKpi
          label="MAX WIN RUN"
          value={`${m.maxWin}d`}
          tone="pos"
          sub="consecutive positive"
        />
        <TmKpi
          label="PROFIT FACTOR"
          value={m.profitFactor.toFixed(2)}
          tone={m.profitFactor > 1 ? "pos" : "neg"}
          sub="Σ gains / |Σ losses|"
        />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── v3 #3 — YEARLY.BREAKDOWN pane ────────────────────────────────── */

function YearlyBreakdownPane({
  equityCurve,
}: {
  readonly equityCurve: readonly import("@/lib/types").EquityCurvePoint[];
}) {
  const { locale } = useLocale();
  const rows: readonly YearStats[] = useMemo(
    () => yearlyStats(equityCurve),
    [equityCurve],
  );
  if (rows.length === 0) return null;
  return (
    <TmPane title="YEARLY.BREAKDOWN" meta={`${rows.length} year${rows.length === 1 ? "" : "s"}`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.yearly.desc")}
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[600px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "80px 60px 80px 90px 90px 80px" }}
        >
          <YHeader>YEAR</YHeader>
          <YHeader align="right">DAYS</YHeader>
          <YHeader align="right">SR</YHeader>
          <YHeader align="right">RETURN</YHeader>
          <YHeader align="right">MAX DD</YHeader>
          <YHeader align="right">HIT</YHeader>
          {rows.map((r) => (
            <YearRow key={r.year} row={r} />
          ))}
        </div>
      </div>
    </TmPane>
  );
}
function YHeader({
  children, align = "left",
}: { readonly children: React.ReactNode; readonly align?: "left" | "right" }) {
  return (
    <div className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted ${align === "right" ? "text-right" : ""}`}>
      {children}
    </div>
  );
}
function YearRow({ row: r }: { readonly row: YearStats }) {
  return (
    <>
      <YCell><span className="text-tm-fg">{r.year}</span></YCell>
      <YCell align="right"><span className="tabular-nums text-tm-muted">{r.nDays}</span></YCell>
      <YCell align="right">
        <span className={`tabular-nums ${r.sharpe > 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {r.sharpe >= 0 ? "+" : ""}{r.sharpe.toFixed(2)}
        </span>
      </YCell>
      <YCell align="right">
        <span className={`tabular-nums ${r.totalReturn > 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {r.totalReturn >= 0 ? "+" : ""}{(r.totalReturn * 100).toFixed(1)}%
        </span>
      </YCell>
      <YCell align="right"><span className="tabular-nums text-tm-neg">{(r.maxDrawdown * 100).toFixed(1)}%</span></YCell>
      <YCell align="right">
        <span className={`tabular-nums ${r.hitRate > 0.5 ? "text-tm-pos" : "text-tm-muted"}`}>
          {(r.hitRate * 100).toFixed(0)}%
        </span>
      </YCell>
    </>
  );
}
function YCell({
  children, align = "left",
}: { readonly children: React.ReactNode; readonly align?: "left" | "right" }) {
  return (
    <div className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-xs ${align === "right" ? "justify-end" : ""}`}>
      {children}
    </div>
  );
}

/* ── v3 #4 — COMPARE.METRICS pane ─────────────────────────────────── */

interface MetricRow {
  readonly label: string;
  readonly a: number;
  readonly b: number;
  readonly fmt: (v: number) => string;
  readonly higherIsBetter: boolean;
}
function CompareMetricsPane({
  primary,
  compare,
}: {
  readonly primary: FactorReport;
  readonly compare: FactorReport;
}) {
  const m = useMemo(() => {
    const aEq = primary.backtest.equity_curve;
    const bEq = compare.backtest.equity_curve;
    const aBench = primary.backtest.benchmark_curve;
    const bBench = compare.backtest.benchmark_curve;
    const aRets = dailyReturns(aEq);
    const bRets = dailyReturns(bEq);
    const aActive = activeReturns(aEq, aBench);
    const bActive = activeReturns(bEq, bBench);
    const aTotal = aEq.length > 0 ? aEq[aEq.length - 1].value / aEq[0].value - 1 : 0;
    const bTotal = bEq.length > 0 ? bEq[bEq.length - 1].value / bEq[0].value - 1 : 0;
    const rows: MetricRow[] = [
      { label: "Total Return", a: aTotal, b: bTotal,
        fmt: (v) => `${(v * 100).toFixed(1)}%`, higherIsBetter: true },
      { label: "Sharpe", a: primary.backtest.test_metrics.sharpe,
        b: compare.backtest.test_metrics.sharpe,
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
      { label: "Sortino", a: sortinoRatio(aRets), b: sortinoRatio(bRets),
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
      { label: "Calmar", a: calmarRatio(aEq), b: calmarRatio(bEq),
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
      { label: "IC (Spearman)", a: primary.backtest.test_metrics.ic_spearman,
        b: compare.backtest.test_metrics.ic_spearman,
        fmt: (v) => v.toFixed(4), higherIsBetter: true },
      { label: "Max Drawdown",
        a: primary.backtest.test_metrics.max_drawdown ?? 0,
        b: compare.backtest.test_metrics.max_drawdown ?? 0,
        fmt: (v) => `${(v * 100).toFixed(1)}%`, higherIsBetter: true },
      { label: "Turnover",
        a: primary.backtest.test_metrics.turnover ?? 0,
        b: compare.backtest.test_metrics.turnover ?? 0,
        fmt: (v) => v.toFixed(3), higherIsBetter: false },
      { label: "Hit Rate",
        a: primary.backtest.test_metrics.hit_rate ?? 0,
        b: compare.backtest.test_metrics.hit_rate ?? 0,
        fmt: (v) => `${(v * 100).toFixed(0)}%`, higherIsBetter: true },
      { label: "Information Ratio", a: informationRatio(aActive),
        b: informationRatio(bActive),
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
      { label: "Tracking Error", a: trackingError(aActive),
        b: trackingError(bActive),
        fmt: (v) => `${(v * 100).toFixed(1)}%`, higherIsBetter: false },
      { label: "α (annualized)",
        a: primary.backtest.alpha_annualized ?? 0,
        b: compare.backtest.alpha_annualized ?? 0,
        fmt: (v) => `${(v * 100).toFixed(2)}%`, higherIsBetter: true },
      { label: "α-t",
        a: primary.backtest.alpha_t_stat ?? 0,
        b: compare.backtest.alpha_t_stat ?? 0,
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
      { label: "β (market)",
        a: Math.abs(primary.backtest.beta_market ?? 0),
        b: Math.abs(compare.backtest.beta_market ?? 0),
        fmt: (v) => v.toFixed(3), higherIsBetter: false },
      { label: "Skew", a: skewness(aRets), b: skewness(bRets),
        fmt: (v) => v.toFixed(2), higherIsBetter: true },
    ];
    return rows;
  }, [primary, compare]);

  return (
    <TmPane
      title="COMPARE.METRICS"
      meta={`${primary.name} vs ${compare.name} · 14 metrics · winner glyph by directionality`}
    >
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[640px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "minmax(160px, 200px) minmax(110px, 130px) minmax(110px, 130px) minmax(80px, 100px) 30px" }}
        >
          <CHeader>METRIC</CHeader>
          <CHeader align="right">{primary.name.slice(0, 16)}</CHeader>
          <CHeader align="right">{compare.name.slice(0, 16)}</CHeader>
          <CHeader align="right">Δ</CHeader>
          <CHeader>·</CHeader>
          {m.map((row) => (
            <MetricCompareRow key={row.label} row={row} />
          ))}
        </div>
      </div>
    </TmPane>
  );
}
function CHeader({
  children, align = "left",
}: { readonly children: React.ReactNode; readonly align?: "left" | "right" }) {
  return (
    <div className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted ${align === "right" ? "text-right" : ""}`}>
      {children}
    </div>
  );
}
function MetricCompareRow({ row }: { readonly row: MetricRow }) {
  const delta = row.a - row.b;
  const aWins = row.higherIsBetter ? row.a > row.b : row.a < row.b;
  const bWins = row.higherIsBetter ? row.b > row.a : row.b < row.a;
  const aTone = aWins ? "text-tm-pos" : "text-tm-fg-2";
  const bTone = bWins ? "text-tm-pos" : "text-tm-fg-2";
  // Δ tone: negative when "higher is better" and a < b, etc.
  const deltaTone = row.higherIsBetter
    ? delta > 0 ? "text-tm-pos" : delta < 0 ? "text-tm-neg" : "text-tm-muted"
    : delta < 0 ? "text-tm-pos" : delta > 0 ? "text-tm-neg" : "text-tm-muted";
  const winner = aWins ? "A" : bWins ? "B" : "·";
  const winnerTone = aWins ? "text-tm-pos" : bWins ? "text-tm-info" : "text-tm-muted";
  return (
    <>
      <div className="flex items-center bg-tm-bg px-2 py-1 font-tm-mono text-xs text-tm-fg">
        {row.label}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-xs tabular-nums ${aTone}`}>
        {row.fmt(row.a)}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-xs tabular-nums ${bTone}`}>
        {row.fmt(row.b)}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-xs tabular-nums ${deltaTone}`}>
        {delta >= 0 ? "+" : ""}{row.fmt(delta).replace(/^[+-]/, "")}
      </div>
      <div className={`flex items-center justify-center bg-tm-bg px-2 py-1 font-tm-mono text-xs font-semibold ${winnerTone}`}>
        {winner}
      </div>
    </>
  );
}

/* ── v3 #5 — COMPARE.CORRELATION pane ─────────────────────────────── */

const CORR_WINDOW = 60;
function CompareCorrelationPane({
  primary,
  compare,
}: {
  readonly primary: FactorReport;
  readonly compare: FactorReport;
}) {
  const { locale } = useLocale();
  const stats = useMemo(() => {
    const aRets = dailyReturns(primary.backtest.equity_curve);
    const bRets = dailyReturns(compare.backtest.equity_curve);
    const n = Math.min(aRets.length, bRets.length);
    const a = aRets.slice(aRets.length - n);
    const b = bRets.slice(bRets.length - n);
    const fullCorr = pearsonCorr(a, b);
    const rolling = rollingCorr(a, b, CORR_WINDOW);
    const series = rolling.map((r) => ({
      idx: r.i,
      date: primary.backtest.equity_curve[r.i + 1]?.date ?? String(r.i),
      corr: r.corr,
    }));
    const minCorr = series.length > 0 ? Math.min(...series.map((s) => s.corr)) : 0;
    const maxCorr = series.length > 0 ? Math.max(...series.map((s) => s.corr)) : 0;
    return { fullCorr, series, minCorr, maxCorr };
  }, [primary, compare]);
  const concentrationWarn = stats.fullCorr > 0.8;
  return (
    <TmPane
      title="COMPARE.CORRELATION"
      meta={`full-period ρ = ${stats.fullCorr.toFixed(3)}${concentrationWarn ? " · ⚠ HIGH" : ""}`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.correlation.desc")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label="ρ FULL"
          value={stats.fullCorr.toFixed(3)}
          tone={stats.fullCorr > 0.8 ? "warn" : stats.fullCorr < 0.3 ? "pos" : "default"}
          sub="entire test slice"
        />
        <TmKpi
          label="ρ MAX"
          value={stats.maxCorr.toFixed(3)}
          sub={`${CORR_WINDOW}d rolling max`}
        />
        <TmKpi
          label="ρ MIN"
          value={stats.minCorr.toFixed(3)}
          sub={`${CORR_WINDOW}d rolling min`}
        />
        <TmKpi
          label="ρ RANGE"
          value={(stats.maxCorr - stats.minCorr).toFixed(3)}
          sub="instability proxy"
        />
      </TmKpiGrid>
      <div className="h-[180px] w-full px-1 pb-2 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={stats.series}
            margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              interval="preserveStartEnd"
              minTickGap={40}
              stroke="var(--tm-rule)"
            />
            <YAxis
              tick={{ fontSize: 12, fill: "var(--tm-muted)" }}
              domain={[-1, 1]}
              tickFormatter={(v: number) => v.toFixed(1)}
              stroke="var(--tm-rule)"
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 12,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
              formatter={(v) =>
                typeof v === "number" ? v.toFixed(3) : String(v ?? "")
              }
            />
            <ReferenceLine y={0} stroke="var(--tm-rule-2)" strokeWidth={1} />
            <ReferenceLine
              y={0.8}
              stroke="var(--tm-warn)"
              strokeDasharray="4 4"
              strokeWidth={1}
            />
            <Line
              type="monotone"
              dataKey="corr"
              stroke={concentrationWarn ? "var(--tm-warn)" : "var(--tm-accent)"}
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

/* ── v3 #6 — RECENT.MOMENTUM pane ─────────────────────────────────── */

function RecentMomentumPane({ report }: { readonly report: FactorReport }) {
  const { locale } = useLocale();
  const eq = report.backtest.equity_curve;
  const bench = report.backtest.benchmark_curve;
  const m = useMemo(() => {
    const r30 = periodReturn(eq, 30);
    const r60 = periodReturn(eq, 60);
    const r90 = periodReturn(eq, 90);
    const r180 = periodReturn(eq, 180);
    const b30 = periodReturn(bench, 30);
    const b60 = periodReturn(bench, 60);
    const b90 = periodReturn(bench, 90);
    const b180 = periodReturn(bench, 180);
    return {
      d30: { f: r30, b: b30, spread: r30 - b30 },
      d60: { f: r60, b: b60, spread: r60 - b60 },
      d90: { f: r90, b: b90, spread: r90 - b90 },
      d180: { f: r180, b: b180, spread: r180 - b180 },
    };
  }, [eq, bench]);
  return (
    <TmPane
      title="RECENT.MOMENTUM"
      meta={`vs ${report.backtest.benchmark_ticker} · spread = factor − benchmark`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.momentum.desc")}
      </p>
      <TmKpiGrid>
        {(
          [
            ["LAST 30D", m.d30],
            ["LAST 60D", m.d60],
            ["LAST 90D", m.d90],
            ["LAST 180D", m.d180],
          ] as const
        ).map(([label, v]) => (
          <TmKpi
            key={label}
            label={label}
            value={`${(v.f * 100).toFixed(1)}%`}
            tone={v.spread > 0 ? "pos" : v.spread < 0 ? "neg" : "default"}
            sub={`bench ${(v.b * 100).toFixed(1)}% · spread ${v.spread >= 0 ? "+" : ""}${(v.spread * 100).toFixed(1)}%`}
          />
        ))}
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── v3 #7 — TICKER.OVERLAP pane ──────────────────────────────────── */

function TickerOverlapPane({
  primary,
  compare,
}: {
  readonly primary: FactorReport;
  readonly compare: FactorReport;
}) {
  const { locale } = useLocale();
  const data = useMemo(() => {
    const aLong = primary.today.top.map((t) => t.ticker);
    const bLong = compare.today.top.map((t) => t.ticker);
    const aShort = primary.today.bottom.map((t) => t.ticker);
    const bShort = compare.today.bottom.map((t) => t.ticker);
    return {
      longJaccard: jaccard(aLong, bLong),
      shortJaccard: jaccard(aShort, bShort),
      longBoth: intersection(aLong, bLong),
      shortBoth: intersection(aShort, bShort),
      crossPos: intersection(aLong, bShort), // primary long + compare short
      crossNeg: intersection(aShort, bLong), // primary short + compare long
      aLongCount: aLong.length,
      bLongCount: bLong.length,
      aShortCount: aShort.length,
      bShortCount: bShort.length,
    };
  }, [primary, compare]);
  const longWarn = data.longJaccard > 0.5;
  const shortWarn = data.shortJaccard > 0.5;
  return (
    <TmPane
      title="TICKER.OVERLAP"
      meta={`Jaccard long ${(data.longJaccard * 100).toFixed(0)}% · short ${(data.shortJaccard * 100).toFixed(0)}%`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.overlap.desc")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label="LONG OVERLAP"
          value={`${data.longBoth.length}/${Math.max(data.aLongCount, data.bLongCount)}`}
          tone={longWarn ? "warn" : "default"}
          sub={`Jaccard ${(data.longJaccard * 100).toFixed(0)}%`}
        />
        <TmKpi
          label="SHORT OVERLAP"
          value={`${data.shortBoth.length}/${Math.max(data.aShortCount, data.bShortCount)}`}
          tone={shortWarn ? "warn" : "default"}
          sub={`Jaccard ${(data.shortJaccard * 100).toFixed(0)}%`}
        />
        <TmKpi
          label="A-LONG ∩ B-SHORT"
          value={data.crossPos.length.toString()}
          tone={data.crossPos.length > 0 ? "warn" : "default"}
          sub="opposite views"
        />
        <TmKpi
          label="A-SHORT ∩ B-LONG"
          value={data.crossNeg.length.toString()}
          tone={data.crossNeg.length > 0 ? "warn" : "default"}
          sub="opposite views"
        />
      </TmKpiGrid>
      {(data.longBoth.length > 0 || data.shortBoth.length > 0) && (
        <div className="grid grid-cols-1 gap-px border-t border-tm-rule bg-tm-rule lg:grid-cols-2">
          <OverlapList title="BOTH LONG" tickers={data.longBoth} tone="pos" />
          <OverlapList title="BOTH SHORT" tickers={data.shortBoth} tone="neg" />
        </div>
      )}
    </TmPane>
  );
}
function OverlapList({
  title, tickers, tone,
}: {
  readonly title: string;
  readonly tickers: readonly string[];
  readonly tone: "pos" | "neg";
}) {
  const accent = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className="bg-tm-bg px-3 py-2">
      <div className={`mb-1 font-tm-mono text-xs font-semibold uppercase tracking-[0.06em] ${accent}`}>
        {title} · {tickers.length}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tickers.length === 0 ? (
          <span className="font-tm-mono text-xs text-tm-muted">none</span>
        ) : (
          tickers.map((tk) => (
            <span
              key={tk}
              className={`border border-tm-rule bg-tm-bg-2 px-1.5 py-px font-tm-mono text-xs tabular-nums ${accent}`}
            >
              {tk}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

/* ── v3 #8 — RECOVERY.STATS pane ──────────────────────────────────── */

function RecoveryStatsPane({
  equityCurve,
}: {
  readonly equityCurve: readonly import("@/lib/types").EquityCurvePoint[];
}) {
  const { locale } = useLocale();
  const s = useMemo(() => recoveryStats(equityCurve), [equityCurve]);
  return (
    <TmPane
      title="RECOVERY.STATS"
      meta={`${s.nDrawdownEpisodes} episodes · ${equityCurve.length} sessions`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "report.recovery.desc")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label="EPISODES"
          value={s.nDrawdownEpisodes.toString()}
          sub="distinct drawdowns"
        />
        <TmKpi
          label="AVG RECOVERY"
          value={s.avgRecoveryDays != null ? `${s.avgRecoveryDays.toFixed(0)}d` : "—"}
          sub="trough → prior peak"
        />
        <TmKpi
          label="LONGEST UW"
          value={`${s.longestUnderwaterDays}d`}
          tone={s.longestUnderwaterDays > 60 ? "warn" : "default"}
          sub="max underwater stretch"
        />
        <TmKpi
          label="DAYS @ HIGH"
          value={`${s.daysSinceLastHigh}d`}
          tone={s.daysSinceLastHigh === 0 ? "pos" : s.daysSinceLastHigh > 30 ? "warn" : "default"}
          sub="0 = at high right now"
        />
      </TmKpiGrid>
    </TmPane>
  );
}
