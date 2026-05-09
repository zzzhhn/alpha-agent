"use client";

/**
 * Report page — workstation port (Stage 3 · 8/9).
 *
 * Tear-sheet generator. Two slots: "primary" (the headline factor) and
 * "compare" (an optional second factor for side-by-side overlay).
 * Both slots run through fetchAll() which spawns runFactorBacktest +
 * signalToday + signalExposure in parallel.
 *
 * Layout: TmSubbar (factor name + universe + status pills + print
 * button) → REPORT.PICKER pane (config chips + example chips + zoo
 * chips + custom-input + compare chips) → COMPARE.OVERLAY pane (when
 * both slots filled) → primary tearsheet sequence (REPORT.COVER →
 * BACKTEST.KPI → EQUITY.UNDERWATER (FactorPnLChart wrapped) →
 * DRAWDOWN → MONTHLY → SIGNAL.TODAY → EXPOSURE) → compare tearsheet.
 *
 * Behavior preserved byte-for-byte: REPORT_PREFILL_KEY handoff from
 * /factors, ReportConfig propagation, fetchAll triple-fetch, print
 * via window.print(), example loadExample auto-runs with locale-
 * appropriate intuition, zoo-entry handoff, compare slot management.
 *
 * NOTE: this is the LAST page using legacy BacktestKpiStrip /
 * DrawdownChart / MonthlyReturnsHeatmap / TopBottomTable /
 * ExposureChart / CompareEquityChart imports. After this port lands,
 * the legacy components are dead code and can be removed in S5 polish.
 */

import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
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
  TmChip,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton } from "@/components/tm/TmButton";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { TmBacktestKpiStrip } from "@/components/backtest/TmBacktestKpiStrip";
import { TmDrawdownChart } from "@/components/backtest/TmDrawdownChart";
import { TmMonthlyReturnsHeatmap } from "@/components/backtest/TmMonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { TmCompareEquityChart } from "@/components/charts/TmCompareEquityChart";
import { TmTopBottomTable } from "@/components/signal/TmTopBottomTable";
import { TmExposureChart } from "@/components/signal/TmExposureChart";
import { listZoo, type ZooEntry } from "@/lib/factor-zoo";
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

  useEffect(() => {
    setZoo(listZoo());
  }, []);

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
    ) => {
      setRunning(true);
      setError(null);
      const [bt, td, ex] = await fetchAll(name, expression, hypothesis, config);
      if (
        bt.error || td.error || ex.error ||
        !bt.data || !td.data || !ex.data
      ) {
        setError(bt.error ?? td.error ?? ex.error ?? "unknown error");
        setRunning(false);
        return;
      }
      const built: FactorReport = {
        name,
        expression,
        intuition: intuitionForCover ?? hypothesis,
        backtest: bt.data,
        today: td.data,
        exposure: ex.data,
      };
      if (slot === "primary") {
        setPrimary(built);
        setCompare(null);
      } else {
        setCompare(built);
      }
      setRunning(false);
    },
    [config],
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

  function loadExample(example: FactorExample) {
    setFactorName(example.name);
    setExpr(example.expression);
    const intu =
      locale === "zh" ? example.intuitionZh : example.intuitionEn;
    setIntuition(intu);
    // v3: pull example's proven config too so the report matches the
    // verdict the example was discovered under.
    setConfig((c) => ({
      direction: example.direction ?? c.direction,
      neutralize: example.neutralize ?? c.neutralize,
      benchmarkTicker: example.benchmarkTicker ?? c.benchmarkTicker,
      transactionCostBps: example.transactionCostBps ?? c.transactionCostBps,
    }));
    void generate(
      example.name,
      example.expression,
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
      "primary",
      intu, // long display text on the cover; backend hypothesis stays short
    );
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
      `tearsheet for ${name}`,
      "primary",
      intuition,
    );
  }

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">REPORT</span>
        <TmSubbarSep />
        <TmSubbarKV
          label="FACTOR"
          value={primary?.name ?? factorName ?? "—"}
        />
        {primary && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="UNIVERSE"
              value={`${primary.today.universe_size}`}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label="SHARPE"
              value={primary.backtest.test_metrics.sharpe.toFixed(2)}
            />
          </>
        )}
        {compare && (
          <>
            <TmSubbarSep />
            <TmSubbarKV label="COMPARE" value={compare.name} />
          </>
        )}
        <TmSubbarSpacer />
        {primary?.backtest.overfit_flag && (
          <TmStatusPill tone="err">
            OVERFIT · OOS DECAY{" "}
            {((primary.backtest.oos_decay ?? 0) * 100).toFixed(0)}%
          </TmStatusPill>
        )}
        {primary && (
          <TmStatusPill
            tone={primary.backtest.survivorship_corrected ? "ok" : "warn"}
          >
            {primary.backtest.survivorship_corrected
              ? `SP500-AS-OF · ${primary.backtest.membership_as_of ?? "—"}`
              : "LEGACY"}
          </TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        {error && <TmStatusPill tone="err">ERROR</TmStatusPill>}
        {primary && (
          <TmButton
            variant="ghost"
            onClick={() => window.print()}
            className="-my-1 px-2"
          >
            {t(locale, "report.exportPdf")}
          </TmButton>
        )}
      </TmSubbar>

      <ReportPickerPane
        factorName={factorName}
        onFactorName={setFactorName}
        expr={expr}
        onExpr={setExpr}
        config={config}
        onConfig={setConfig}
        zoo={zoo}
        primary={primary}
        compare={compare}
        running={running}
        loadExample={loadExample}
        loadZooEntry={loadZooEntry}
        runCustom={runCustom}
        generate={generate}
        clearCompare={() => setCompare(null)}
      />

      {error && (
        <TmPane title="ERROR" meta="report generation failed">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      {primary && compare && (
        <TmPane
          title="COMPARE.OVERLAY"
          meta={`${primary.name} vs ${compare.name} vs ${primary.backtest.benchmark_ticker}`}
        >
          <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
            {t(locale, "report.compare.subtitle")
              .replace("{a}", primary.name)
              .replace("{b}", compare.name)}
          </p>
          <TmCompareEquityChart
            factor1Name={primary.name}
            factor1={primary.backtest.equity_curve}
            factor2Name={compare.name}
            factor2={compare.backtest.equity_curve}
            benchmark={primary.backtest.benchmark_curve}
            benchmarkTicker={primary.backtest.benchmark_ticker}
          />
        </TmPane>
      )}

      {/* v3 #4 — side-by-side metric table */}
      {primary && compare && (
        <CompareMetricsPane primary={primary} compare={compare} />
      )}

      {/* v3 #5 — rolling correlation between primary + compare daily returns */}
      {primary && compare && (
        <CompareCorrelationPane primary={primary} compare={compare} />
      )}

      {/* v3 #7 — ticker overlap (Jaccard + intersect names) */}
      {primary && compare && (
        <TickerOverlapPane primary={primary} compare={compare} />
      )}

      {primary && (
        <article className="report-tearsheet flex flex-col">
          <ReportCoverPane
            r={primary}
            expr={primary.expression}
            factorName={primary.name}
            intuition={primary.intuition}
            config={config}
          />
          <TmBacktestKpiStrip result={primary.backtest} />
          {/* v3 #1 — institutional risk metrics */}
          <RiskMetricsPane report={primary} />
          {/* v3 #2 — tail risk + streak diagnostics */}
          <TailRiskPane report={primary} />
          {/* v3 #6 — recent momentum vs benchmark */}
          <RecentMomentumPane report={primary} />
          <TmPane
            title="EQUITY.CURVE"
            meta={`${primary.backtest.equity_curve.length} sessions · vs ${primary.backtest.benchmark_ticker}`}
          >
            <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
              {t(locale, "backtest.equity.subtitle")}
            </p>
            <div className="px-2 pb-2 pt-2">
              <FactorPnLChart data={primary.backtest} height={260} />
            </div>
          </TmPane>
          <TmDrawdownChart equityCurve={primary.backtest.equity_curve} />
          {/* v3 #8 — recovery / underwater stats */}
          <RecoveryStatsPane equityCurve={primary.backtest.equity_curve} />
          {/* v3 #3 — per-year breakdown table */}
          <YearlyBreakdownPane equityCurve={primary.backtest.equity_curve} />
          {primary.backtest.monthly_returns &&
            primary.backtest.monthly_returns.length > 0 && (
              <TmMonthlyReturnsHeatmap
                data={primary.backtest.monthly_returns}
              />
            )}
          <TmTopBottomTable today={primary.today} loading={false} />
          <TmExposureChart
            data={primary.exposure}
            topN={10}
            loading={false}
          />
        </article>
      )}

      {compare && (
        <article className="report-tearsheet flex flex-col">
          <TmPane title="REPORT.COMPARE" meta="second factor tear sheet">
            <p className="px-3 py-2 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-info">
              {t(locale, "report.compare.secondLabel")}
            </p>
          </TmPane>
          <ReportCoverPane
            r={compare}
            expr={compare.expression}
            factorName={compare.name}
            intuition={compare.intuition}
            config={config}
          />
          <TmBacktestKpiStrip result={compare.backtest} />
          <TmDrawdownChart equityCurve={compare.backtest.equity_curve} />
          {compare.backtest.monthly_returns &&
            compare.backtest.monthly_returns.length > 0 && (
              <TmMonthlyReturnsHeatmap
                data={compare.backtest.monthly_returns}
              />
            )}
          <TmTopBottomTable today={compare.today} loading={false} />
          <TmExposureChart
            data={compare.exposure}
            topN={10}
            loading={false}
          />
        </article>
      )}

      {!primary && !running && (
        <TmPane title="USAGE" meta="hint">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {t(locale, "report.subtitle")}
          </p>
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── REPORT.PICKER pane ───────────────────────────────────────────── */

function ReportPickerPane({
  factorName,
  onFactorName,
  expr,
  onExpr,
  config,
  onConfig,
  zoo,
  primary,
  compare,
  running,
  loadExample,
  loadZooEntry,
  runCustom,
  generate,
  clearCompare,
}: {
  readonly factorName: string;
  readonly onFactorName: (v: string) => void;
  readonly expr: string;
  readonly onExpr: (v: string) => void;
  readonly config: ReportConfig;
  readonly onConfig: (
    fn: ReportConfig | ((c: ReportConfig) => ReportConfig),
  ) => void;
  readonly zoo: readonly ZooEntry[];
  readonly primary: FactorReport | null;
  readonly compare: FactorReport | null;
  readonly running: boolean;
  readonly loadExample: (e: FactorExample) => void;
  readonly loadZooEntry: (e: ZooEntry, slot: "primary" | "compare") => void;
  readonly runCustom: () => void;
  readonly generate: (
    name: string,
    expression: string,
    hypothesis: string,
    slot: "primary" | "compare",
    intuitionForCover?: string,
  ) => void;
  readonly clearCompare: () => void;
}) {
  const { locale } = useLocale();

  return (
    <TmPane
      title="REPORT.PICKER"
      meta={`${FACTOR_EXAMPLES.length} EXAMPLES · ${zoo.length} ZOO · ${primary ? "GENERATED" : "EMPTY"}`}
    >
      <div className="flex flex-col gap-3 px-3 py-3">
        {/* Config chip rows: direction / neutralize / benchmark / cost */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ConfigChipGroup
            label="direction"
            options={["long_short", "long_only", "short_only"]}
            value={config.direction}
            onChange={(v) => onConfig((c) => ({ ...c, direction: v as ReportConfig["direction"] }))}
          />
          <ConfigChipGroup
            label={t(locale, "backtest.form.neutralize")}
            options={["none", "sector"]}
            value={config.neutralize}
            onChange={(v) => onConfig((c) => ({ ...c, neutralize: v as "none" | "sector" }))}
          />
          <ConfigChipGroup
            label={t(locale, "backtest.form.benchmark")}
            options={["SPY", "RSP"]}
            value={config.benchmarkTicker}
            onChange={(v) => onConfig((c) => ({ ...c, benchmarkTicker: v as "SPY" | "RSP" }))}
          />
          <div className="flex items-center gap-2">
            <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
              cost bps
            </span>
            <input
              type="number"
              min={0}
              max={50}
              step={1}
              value={config.transactionCostBps}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                onConfig((c) => ({
                  ...c,
                  transactionCostBps: Number(e.target.value) || 0,
                }))
              }
              className="h-6 w-14 border border-tm-rule bg-tm-bg-2 px-2 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg outline-none focus:border-tm-accent"
            />
          </div>
        </div>

        {/* From examples */}
        <div className="border-t border-tm-rule pt-2.5">
          <p className="mb-1.5 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "report.picker.fromExamples")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {FACTOR_EXAMPLES.map((example) => (
              <TmChip
                key={example.name}
                onClick={() => loadExample(example)}
                disabled={running}
              >
                {example.name}
              </TmChip>
            ))}
          </div>
        </div>

        {/* From zoo */}
        {zoo.length > 0 && (
          <div className="border-t border-tm-rule pt-2.5">
            <p className="mb-1.5 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "report.picker.fromZoo")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {zoo.slice(0, 12).map((z) => (
                <TmChip
                  key={z.id}
                  onClick={() => loadZooEntry(z, "primary")}
                  disabled={running}
                  title={z.expression}
                >
                  {z.name}
                </TmChip>
              ))}
            </div>
          </div>
        )}

        {/* Custom input */}
        <div className="flex flex-col gap-2 border-t border-tm-rule pt-2.5">
          <input
            type="text"
            value={factorName}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              onFactorName(e.target.value)
            }
            placeholder={t(locale, "report.picker.namePlaceholder")}
            className="h-8 w-full border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11.5px] text-tm-fg outline-none placeholder:text-tm-muted focus:border-tm-accent"
          />
          <textarea
            value={expr}
            onChange={(e) => onExpr(e.target.value)}
            placeholder={t(locale, "report.picker.exprPlaceholder")}
            rows={2}
            spellCheck={false}
            className="w-full resize-none border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg outline-none focus:border-tm-accent"
          />
          <div className="flex justify-end">
            <TmButton
              variant="primary"
              onClick={runCustom}
              disabled={running || expr.trim().length === 0}
            >
              {running
                ? t(locale, "report.picker.running")
                : t(locale, "report.picker.generate")}
            </TmButton>
          </div>
        </div>

        {/* Compare slot — appears once primary is set */}
        {primary && (
          <div className="border-t border-tm-rule pt-2.5">
            <p className="mb-1 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "report.picker.compareTitle")}
            </p>
            <p className="mb-1.5 font-tm-mono text-[10.5px] text-tm-muted">
              {t(locale, "report.picker.compareSubtitle")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {FACTOR_EXAMPLES.filter(
                (e) => e.expression !== primary.expression,
              ).map((example) => (
                <TmChip
                  key={example.name}
                  onClick={() =>
                    generate(
                      example.name,
                      example.expression,
                      locale === "zh"
                        ? example.hypothesisZh
                        : example.hypothesisEn,
                      "compare",
                      locale === "zh"
                        ? example.intuitionZh
                        : example.intuitionEn,
                    )
                  }
                  disabled={running}
                >
                  + {example.name}
                </TmChip>
              ))}
              {zoo
                .filter((z) => z.expression !== primary.expression)
                .slice(0, 6)
                .map((z) => (
                  <TmChip
                    key={z.id}
                    onClick={() => loadZooEntry(z, "compare")}
                    disabled={running}
                  >
                    + {z.name}
                  </TmChip>
                ))}
              {compare && (
                <TmButton
                  variant="ghost"
                  onClick={clearCompare}
                  className="h-6 px-2 text-[10px]"
                >
                  {t(locale, "report.picker.compareClear")}
                </TmButton>
              )}
            </div>
          </div>
        )}
      </div>
    </TmPane>
  );
}

function ConfigChipGroup({
  label,
  options,
  value,
  onChange,
}: {
  readonly label: string;
  readonly options: readonly string[];
  readonly value: string;
  readonly onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </span>
      {options.map((o) => (
        <TmChip key={o} on={value === o} onClick={() => onChange(o)}>
          {o}
        </TmChip>
      ))}
    </div>
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
  const totalRet =
    eq.length > 0 ? eq[eq.length - 1].value / eq[0].value - 1 : 0;
  const benchEq = r.backtest.benchmark_curve;
  const benchRet =
    benchEq.length > 0
      ? benchEq[benchEq.length - 1].value / benchEq[0].value - 1
      : 0;

  return (
    <TmPane
      title="REPORT.COVER"
      meta={`${factorName || r.backtest.factor_name} · ${r.today.universe_size} tickers`}
    >
      <div className="border-b border-tm-rule px-3 py-2.5">
        <h2 className="font-tm-mono text-[14px] font-semibold uppercase tracking-[0.04em] text-tm-accent">
          {factorName || r.backtest.factor_name}
        </h2>
        <code className="mt-1 block break-all font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
          {expr}
        </code>
      </div>

      <TmKpiGrid>
        <TmKpi
          label="UNIVERSE"
          value={r.today.universe_size.toString()}
          sub="SP500 panel"
        />
        <TmKpi
          label="WINDOW"
          value={`${eq.length}d`}
          sub={`${startDate} → ${endDate}`}
        />
        <TmKpi
          label="BENCHMARK"
          value={r.backtest.benchmark_ticker}
          sub={`${(benchRet * 100).toFixed(1)}% over slice`}
        />
        <TmKpi
          label="DIRECTION"
          value={config.direction}
          sub={
            config.neutralize === "sector"
              ? "sector-neutral"
              : "no neutralize"
          }
        />
        <TmKpi
          label="COST"
          value={`${config.transactionCostBps}bps`}
          sub="round-trip"
        />
        <TmKpi
          label="TOTAL RET"
          value={`${(totalRet * 100).toFixed(1)}%`}
          tone={totalRet > benchRet ? "pos" : "neg"}
          sub={`vs ${(benchRet * 100).toFixed(1)}% bench`}
        />
      </TmKpiGrid>

      {intuition && (
        <p className="border-t border-tm-rule px-3 py-2.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
          {intuition}
        </p>
      )}

      <p className="border-t border-tm-rule bg-tm-bg-2 px-3 py-1 font-tm-mono text-[9.5px] uppercase tracking-[0.06em] text-tm-muted">
        {t(locale, "report.cover.generated")}:{" "}
        {new Date().toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}
      </p>
    </TmPane>
  );
}

/* ── v3 #1 — RISK.METRICS pane ────────────────────────────────────── */

function RiskMetricsPane({ report }: { readonly report: FactorReport }) {
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
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Sortino / Calmar / IR / TE / Skew / Excess-Kurt — CFA Performance Standards conventions, complement Sharpe with downside, drawdown, and distribution shape.
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
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Bottom-of-distribution diagnostics. VaR α = α-th percentile worst day. CVaR (Expected Shortfall) = mean of worst α% days, captures tail severity beyond VaR.
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
  const rows: readonly YearStats[] = useMemo(
    () => yearlyStats(equityCurve),
    [equityCurve],
  );
  if (rows.length === 0) return null;
  return (
    <TmPane title="YEARLY.BREAKDOWN" meta={`${rows.length} year${rows.length === 1 ? "" : "s"}`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Per-year stats. Sharpe annualized within each year only — short-year fragments at panel edges may amplify variance.
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
    <div className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${align === "right" ? "text-right" : ""}`}>
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
    <div className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${align === "right" ? "justify-end" : ""}`}>
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
    <div className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${align === "right" ? "text-right" : ""}`}>
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
      <div className="flex items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] text-tm-fg">
        {row.label}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-[11px] tabular-nums ${aTone}`}>
        {row.fmt(row.a)}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-[11px] tabular-nums ${bTone}`}>
        {row.fmt(row.b)}
      </div>
      <div className={`flex items-center justify-end bg-tm-bg px-2 py-1 font-tm-mono text-[10.5px] tabular-nums ${deltaTone}`}>
        {delta >= 0 ? "+" : ""}{row.fmt(delta).replace(/^[+-]/, "")}
      </div>
      <div className={`flex items-center justify-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] font-semibold ${winnerTone}`}>
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
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Pearson correlation of daily returns. ρ ≥ 0.8 = stacking the two factors gives near-zero diversification benefit; ρ near 0 = genuinely independent signals.
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
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              interval="preserveStartEnd"
              minTickGap={40}
              stroke="var(--tm-rule)"
            />
            <YAxis
              tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              domain={[-1, 1]}
              tickFormatter={(v: number) => v.toFixed(1)}
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
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Trailing-window returns to surface late-period direction shifts. Persistent positive spread across all four windows = factor still working; spread reversal = decay signal.
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
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Overlap of today&apos;s top-N baskets between the two factors. High Jaccard (≥0.5) = baskets stack the same names → portfolio diversification benefit minimal even at low correlation.
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
      <div className={`mb-1 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${accent}`}>
        {title} · {tickers.length}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tickers.length === 0 ? (
          <span className="font-tm-mono text-[10.5px] text-tm-muted">none</span>
        ) : (
          tickers.map((tk) => (
            <span
              key={tk}
              className={`border border-tm-rule bg-tm-bg-2 px-1.5 py-px font-tm-mono text-[10.5px] tabular-nums ${accent}`}
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
  const s = useMemo(() => recoveryStats(equityCurve), [equityCurve]);
  return (
    <TmPane
      title="RECOVERY.STATS"
      meta={`${s.nDrawdownEpisodes} episodes · ${equityCurve.length} sessions`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Drawdown episode time analysis. avg recovery = mean sessions from local trough back to prior peak. Longest underwater = max stretch below running peak across all episodes. Days since last high = time since a new equity all-time-high (0 = at high now).
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
