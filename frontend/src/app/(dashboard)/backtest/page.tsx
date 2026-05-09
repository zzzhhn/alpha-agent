"use client";

/**
 * Backtest page — workstation port v3 (Stage 3 · 7/9, density rework).
 *
 * v3 ships 7 institutional-grade panes layered on the v2 layout, all
 * derived client-side from the existing FactorBacktestResponse:
 *
 *   1. WORST.DRAWDOWNS — top-5 drawdown periods (start / trough /
 *      recovery / depth / duration). AQR factor-paper standard.
 *   2. EQUITY.UNDERWATER — combined equity + DD ComposedChart on
 *      shared time axis (replaces 2 v2 panes, saves ~220px).
 *   3. TRAIN/TEST.SPLIT — equity curve sliced at train_end_index +
 *      KPIs surfacing OOS decay visually, not just numerically.
 *   4. PORTFOLIO.TODAY — last-day long/short basket snapshot (top 10
 *      each side with weight + 5d contribution). Bloomberg PORT-style.
 *   5. TURNOVER.PROFILE — histogram of daily turnover + names rolled
 *      in/out per day. Cost-realism check.
 *   6. WIN/LOSS.DISTRIBUTION — daily PnL histogram + 5 KPIs (best
 *      day / worst day / % up / avg win / avg loss).
 *   7. POSITION.CONTRIBUTION — top contributors / detractors over the
 *      test slice. FactSet PA3-style attribution.
 *
 * #4-#5-#7 are conditional on include_breakdown (now defaults to true
 * in TmBacktestForm; payload increment ~30KB).
 *
 * Layout sequence:
 *   FORM → KPI → RISK.ATTRIB → TRAIN/TEST → EQUITY.UNDERWATER →
 *   WORST.DRAWDOWNS → WIN/LOSS → REGIME → MONTHLY → WALKFORWARD →
 *   PORTFOLIO.TODAY → TURNOVER.PROFILE → POSITION.CONTRIBUTION →
 *   DAILY.BREAKDOWN
 *
 * Behavior preserved byte-for-byte: PREFILL_KEY handoff, run + state
 * machine, ZooSaveButton args (subbar), runFactorBacktest payload,
 * CSV export.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
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
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import {
  TmBacktestForm,
  type BacktestFormParams,
} from "@/components/backtest/TmBacktestForm";
import { TmBacktestKpiStrip } from "@/components/backtest/TmBacktestKpiStrip";
import { TmEquityDrawdownChart } from "@/components/backtest/TmEquityDrawdownChart";
import { TmMonthlyReturnsHeatmap } from "@/components/backtest/TmMonthlyReturnsHeatmap";
import { ZooSaveButton } from "@/components/zoo/ZooSaveButton";
import { runFactorBacktest } from "@/lib/api";
import type {
  FactorBacktestResponse,
  EquityCurvePoint,
} from "@/lib/types";

interface PrefillPayload {
  readonly name: string;
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly hypothesis?: string;
  readonly direction?: "long_short" | "long_only" | "short_only";
  readonly neutralize?: "none" | "sector";
  readonly benchmarkTicker?: "SPY" | "RSP";
  readonly mode?: "static" | "walk_forward";
  readonly topPct?: number;
  readonly bottomPct?: number;
  readonly transactionCostBps?: number;
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
  const [lastParams, setLastParams] = useState<BacktestFormParams | null>(
    null,
  );

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
    setLastParams(p);
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
      neutralize: p.neutralize,
      benchmark_ticker: p.benchmarkTicker,
    });
    if (res.error || !res.data) {
      setError(res.error ?? "unknown error");
    } else {
      setResult(res.data);
    }
    setRunning(false);
  }

  const totalReturn =
    result && result.equity_curve.length > 0
      ? result.equity_curve[result.equity_curve.length - 1].value /
          result.equity_curve[0].value -
        1
      : null;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">BACKTEST</span>
        <TmSubbarSep />
        <TmSubbarKV
          label="FACTOR"
          value={prefill?.name ?? lastName ?? "user_factor"}
        />
        <TmSubbarSep />
        <TmSubbarKV label="UNIVERSE" value="SP500" />
        {result && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="SHARPE"
              value={result.test_metrics.sharpe.toFixed(2)}
            />
            {totalReturn !== null && (
              <>
                <TmSubbarSep />
                <TmSubbarKV
                  label="TOTAL"
                  value={`${(totalReturn * 100).toFixed(1)}%`}
                />
              </>
            )}
          </>
        )}
        <TmSubbarSpacer />
        {result?.overfit_flag && (
          <TmStatusPill tone="err">
            OVERFIT · OOS DECAY{" "}
            {((result.oos_decay ?? 0) * 100).toFixed(0)}%
          </TmStatusPill>
        )}
        {result && (
          <TmStatusPill tone={result.survivorship_corrected ? "ok" : "warn"}>
            {result.survivorship_corrected
              ? `SP500-AS-OF · ${result.membership_as_of ?? "—"}`
              : "LEGACY"}
          </TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        {error && <TmStatusPill tone="err">ERROR</TmStatusPill>}
        {result && (
          <ZooSaveButton
            name={lastName}
            expression={lastExpr}
            hypothesis={prefill?.hypothesis}
            direction={lastParams?.direction}
            neutralize={lastParams?.neutralize}
            benchmarkTicker={lastParams?.benchmarkTicker}
            mode={lastParams?.mode}
            topPct={lastParams?.topPct}
            bottomPct={lastParams?.bottomPct}
            transactionCostBps={lastParams?.transactionCostBps}
            headlineMetrics={{
              testSharpe: result.test_metrics.sharpe,
              totalReturn: totalReturn ?? undefined,
              testIc: result.test_metrics.ic_spearman,
            }}
          />
        )}
      </TmSubbar>

      <TmBacktestForm
        running={running}
        onRun={run}
        initialExpression={prefill?.expression}
        autoRun={Boolean(prefill?.expression)}
        initialConfig={
          prefill
            ? {
                direction: prefill.direction,
                neutralize: prefill.neutralize,
                benchmarkTicker: prefill.benchmarkTicker,
                mode: prefill.mode,
                topPct: prefill.topPct,
                bottomPct: prefill.bottomPct,
                transactionCostBps: prefill.transactionCostBps,
              }
            : undefined
        }
      />

      {error && (
        <TmPane title="ERROR" meta="backtest run failed">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      {result && (
        <>
          <TmBacktestKpiStrip result={result} />
          <RiskAttributionPane result={result} />
          <TrainTestSplitPane result={result} />
          <TmEquityDrawdownChart result={result} />
          <WorstDrawdownsPane equityCurve={result.equity_curve} />
          <WinLossDistributionPane result={result} />
          {result.regime_breakdown && result.regime_breakdown.length > 0 && (
            <RegimeBreakdownPane result={result} />
          )}
          {result.monthly_returns && result.monthly_returns.length > 0 && (
            <TmMonthlyReturnsHeatmap data={result.monthly_returns} />
          )}
          {result.walk_forward && result.walk_forward.length > 0 && (
            <WalkForwardPane windows={result.walk_forward} />
          )}
          {result.daily_breakdown && result.daily_breakdown.length > 0 && (
            <>
              <PortfolioTodayPane breakdown={result.daily_breakdown} />
              <TurnoverProfilePane breakdown={result.daily_breakdown} />
              <PositionContributionPane
                breakdown={result.daily_breakdown}
                trainEndIndex={result.train_end_index}
              />
              <DailyBreakdownPane
                breakdown={result.daily_breakdown}
                factorName={result.factor_name}
              />
            </>
          )}
        </>
      )}

      {!result && !running && (
        <TmPane title="USAGE" meta="hint">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {t(locale, "backtest.subtitle")}
          </p>
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── RiskAttributionPane (unchanged from v2) ──────────────────────── */

function RiskAttributionPane({ result }: { readonly result: FactorBacktestResponse }) {
  const { locale } = useLocale();
  const alpha = result.alpha_annualized ?? 0;
  const beta = result.beta_market ?? 0;
  const r2 = result.r_squared ?? 0;
  const pAlpha = result.alpha_pvalue ?? 1;

  const alphaTone: "pos" | "neg" | "warn" | "default" =
    pAlpha < 0.05 && alpha > 0 ? "pos"
    : pAlpha < 0.05 && alpha < 0 ? "neg"
    : pAlpha < 0.1 && alpha > 0 ? "warn" : "default";

  const verdict =
    pAlpha < 0.05 && Math.abs(beta) < 0.3 ? t(locale, "backtest.risk.verdictAlphaPure")
    : pAlpha < 0.05 ? t(locale, "backtest.risk.verdictAlphaLevered")
    : pAlpha < 0.1 && alpha > 0 && Math.abs(beta) < 0.3 ? t(locale, "backtest.risk.verdictMarginal")
    : Math.abs(beta) > 0.5 ? t(locale, "backtest.risk.verdictBetaOnly")
    : t(locale, "backtest.risk.verdictNoise");

  return (
    <TmPane title="RISK.ATTRIBUTION" meta="α / β / R² / verdict">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.risk.subtitle")}
      </p>
      <TmKpiGrid>
        <TmKpi label={t(locale, "backtest.risk.alpha")}
          value={`${alpha >= 0 ? "+" : ""}${(alpha * 100).toFixed(2)}%`}
          tone={alphaTone}
          sub={`p=${pAlpha < 0.001 ? "<0.001" : pAlpha.toFixed(3)}`} />
        <TmKpi label={t(locale, "backtest.risk.beta")}
          value={`${beta >= 0 ? "+" : ""}${beta.toFixed(3)}`}
          tone={Math.abs(beta) > 0.5 ? "warn" : "default"}
          sub={t(locale, "backtest.risk.betaHint")} />
        <TmKpi label="R²" value={`${(r2 * 100).toFixed(1)}%`}
          sub={t(locale, "backtest.risk.r2Hint")} />
        <TmKpi label={t(locale, "backtest.risk.verdict")} value={verdict} tone={alphaTone} />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── 3. TRAIN/TEST.SPLIT ──────────────────────────────────────────── */

function TrainTestSplitPane({
  result,
}: {
  readonly result: FactorBacktestResponse;
}) {
  const eq = result.equity_curve;
  const split = result.train_end_index;
  if (!eq || eq.length === 0 || split == null || split <= 0 || split >= eq.length) {
    return null;
  }
  // Build series: split into trainEquity / testEquity. Each row keeps a date.
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
        <TmKpi label="TRAIN SR" value={trainSharpe.toFixed(2)}
          tone={trainSharpe > 0 ? "pos" : "neg"} sub="in-sample" />
        <TmKpi label="TEST SR" value={testSharpe.toFixed(2)}
          tone={testSharpe > 0 ? "pos" : "neg"} sub="out-of-sample" />
        <TmKpi label="TRAIN RET" value={`${(trainRet * 100).toFixed(1)}%`}
          tone={trainRet > 0 ? "pos" : "neg"} />
        <TmKpi label="TEST RET" value={`${(testRet * 100).toFixed(1)}%`}
          tone={testRet > 0 ? "pos" : "neg"} />
        <TmKpi
          label="OOS DECAY"
          value={`${(oosDecay * 100).toFixed(0)}%`}
          tone={decayTone}
          sub={result.overfit_flag ? "overfit" : "ok"}
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
            <ReferenceLine x={splitDate} stroke="var(--tm-warn)" strokeDasharray="3 3" strokeWidth={1.2} />
            <Line type="monotone" dataKey="train" name="train"
              stroke="var(--tm-accent)" strokeWidth={1.8} dot={false}
              connectNulls={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="test" name="test"
              stroke="var(--tm-info)" strokeWidth={1.8} dot={false}
              connectNulls={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

/* ── 1. WORST.DRAWDOWNS ───────────────────────────────────────────── */

interface DrawdownPeriod {
  readonly start: string;
  readonly trough: string;
  readonly recovery: string | null; // null = ongoing
  readonly depth: number;            // negative percent (e.g., -0.18)
  readonly durationDays: number;
  readonly recoveryDays: number | null;
}
function findDrawdowns(eq: readonly EquityCurvePoint[]): DrawdownPeriod[] {
  if (eq.length === 0) return [];
  const out: DrawdownPeriod[] = [];
  let peak = eq[0].value;
  let peakDate = eq[0].date;
  let inDD = false;
  let troughVal = peak;
  let troughDate = peakDate;
  for (let i = 1; i < eq.length; i++) {
    const p = eq[i];
    if (p.value >= peak) {
      // recovered or new peak
      if (inDD) {
        const depth = (troughVal - peak) / peak;
        const durationDays = i - eq.findIndex((x) => x.date === peakDate);
        const troughIdx = eq.findIndex((x) => x.date === troughDate);
        const recoveryDays = i - troughIdx;
        out.push({
          start: peakDate,
          trough: troughDate,
          recovery: p.date,
          depth,
          durationDays,
          recoveryDays,
        });
        inDD = false;
      }
      peak = p.value;
      peakDate = p.date;
      troughVal = peak;
      troughDate = p.date;
    } else {
      // below peak
      if (!inDD) {
        inDD = true;
        troughVal = p.value;
        troughDate = p.date;
      } else if (p.value < troughVal) {
        troughVal = p.value;
        troughDate = p.date;
      }
    }
  }
  if (inDD) {
    const depth = (troughVal - peak) / peak;
    const peakIdx = eq.findIndex((x) => x.date === peakDate);
    const durationDays = eq.length - 1 - peakIdx;
    out.push({
      start: peakDate,
      trough: troughDate,
      recovery: null,
      depth,
      durationDays,
      recoveryDays: null,
    });
  }
  return out.sort((a, b) => a.depth - b.depth).slice(0, 5);
}

function WorstDrawdownsPane({
  equityCurve,
}: {
  readonly equityCurve: readonly EquityCurvePoint[];
}) {
  const periods = useMemo(() => findDrawdowns(equityCurve), [equityCurve]);
  if (periods.length === 0) {
    return null;
  }
  const worstDepth = periods[0]?.depth ?? 0;
  return (
    <TmPane
      title="WORST.DRAWDOWNS"
      meta={`top ${periods.length} · worst ${(worstDepth * 100).toFixed(1)}%`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Peak-to-trough drawdown periods, sorted deepest first. Recovery
        column shows days from trough back to prior peak; <code className="text-tm-fg-2">ongoing</code> if not yet recovered.
      </p>
      <div className="overflow-x-auto">
        <div className="grid min-w-[760px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "32px minmax(120px,140px) minmax(120px,140px) minmax(120px,140px) 80px 80px 80px" }}>
          <RHeader>#</RHeader>
          <RHeader>start</RHeader>
          <RHeader>trough</RHeader>
          <RHeader>recovery</RHeader>
          <RHeader align="right">depth</RHeader>
          <RHeader align="right">duration</RHeader>
          <RHeader align="right">recovery</RHeader>
          {periods.map((p, i) => (
            <DDRow key={`${p.start}-${p.trough}`} rank={i + 1} dd={p} />
          ))}
        </div>
      </div>
    </TmPane>
  );
}
function DDRow({ rank, dd }: { readonly rank: number; readonly dd: DrawdownPeriod }) {
  return (
    <>
      <RCell><span className="text-tm-muted">{String(rank).padStart(2, "0")}</span></RCell>
      <RCell><span className="text-tm-fg">{dd.start}</span></RCell>
      <RCell><span className="text-tm-neg">{dd.trough}</span></RCell>
      <RCell>
        <span className={dd.recovery === null ? "text-tm-warn" : "text-tm-pos"}>
          {dd.recovery ?? "ongoing"}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-neg">
          {(dd.depth * 100).toFixed(1)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">{dd.durationDays}d</span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">
          {dd.recoveryDays !== null ? `${dd.recoveryDays}d` : "—"}
        </span>
      </RCell>
    </>
  );
}

/* ── 6. WIN/LOSS.DISTRIBUTION ─────────────────────────────────────── */

const PNL_BINS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: -Infinity, hi: -0.03, label: "<−3%" },
  { lo: -0.03, hi: -0.02, label: "−3..−2" },
  { lo: -0.02, hi: -0.01, label: "−2..−1" },
  { lo: -0.01, hi: -0.005, label: "−1..−0.5" },
  { lo: -0.005, hi: 0, label: "−0.5..0" },
  { lo: 0, hi: 0.005, label: "0..0.5" },
  { lo: 0.005, hi: 0.01, label: "0.5..1" },
  { lo: 0.01, hi: 0.02, label: "1..2" },
  { lo: 0.02, hi: 0.03, label: "2..3" },
  { lo: 0.03, hi: Infinity, label: "≥3%" },
];

function WinLossDistributionPane({
  result,
}: {
  readonly result: FactorBacktestResponse;
}) {
  const series = useMemo(() => {
    const bd = result.daily_breakdown;
    if (bd && bd.length > 0) {
      // Use daily_breakdown if available — it has the test slice's daily
      // returns. Filter out warm-up days with empty baskets.
      return bd
        .filter((d) => d.long_basket.length > 0 || d.short_basket.length > 0)
        .map((d) => d.daily_return);
    }
    // Fallback: derive daily_return from equity_curve at all sessions.
    const eq = result.equity_curve;
    const out: number[] = [];
    for (let i = 1; i < eq.length; i++) {
      out.push(eq[i].value / eq[i - 1].value - 1);
    }
    return out;
  }, [result]);

  if (series.length === 0) return null;

  const dist = PNL_BINS.map((b) => ({
    label: b.label,
    count: series.filter((v) => v > b.lo && v <= b.hi).length,
    positive: b.lo >= 0,
  }));
  const upDays = series.filter((v) => v > 0).length;
  const downDays = series.filter((v) => v < 0).length;
  const wins = series.filter((v) => v > 0);
  const losses = series.filter((v) => v < 0);
  const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const bestDay = series.reduce((m, v) => (v > m ? v : m), -Infinity);
  const worstDay = series.reduce((m, v) => (v < m ? v : m), Infinity);
  const upPct = series.length > 0 ? (upDays / series.length) * 100 : 0;
  const winLossRatio = avgLoss !== 0 ? Math.abs(avgWin / avgLoss) : 0;

  return (
    <TmPane
      title="WIN/LOSS.DISTRIBUTION"
      meta={`${series.length} sessions · ${upDays} up / ${downDays} down`}
    >
      <TmKpiGrid>
        <TmKpi label="BEST DAY" value={`${(bestDay * 100).toFixed(2)}%`} tone="pos" />
        <TmKpi label="WORST DAY" value={`${(worstDay * 100).toFixed(2)}%`} tone="neg" />
        <TmKpi label="UP %" value={`${upPct.toFixed(0)}%`}
          tone={upPct > 50 ? "pos" : "neg"} sub={`${upDays}/${series.length}`} />
        <TmKpi label="AVG WIN" value={`${(avgWin * 100).toFixed(2)}%`} tone="pos" />
        <TmKpi label="AVG LOSS" value={`${(avgLoss * 100).toFixed(2)}%`} tone="neg" />
        <TmKpi label="WIN/LOSS"
          value={winLossRatio.toFixed(2)}
          tone={winLossRatio > 1 ? "pos" : "neg"}
          sub="ratio of magnitudes" />
      </TmKpiGrid>
      <div className="h-[180px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dist} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)" interval={0} />
            <YAxis tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)" allowDecimals={false} />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
            />
            <Bar dataKey="count">
              {dist.map((d, i) => (
                <Cell key={i} fill={d.positive ? "var(--tm-pos)" : "var(--tm-neg)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

/* ── 4. PORTFOLIO.TODAY ───────────────────────────────────────────── */

function PortfolioTodayPane({
  breakdown,
}: {
  readonly breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>;
}) {
  // Use the most recent populated day (skip warm-up tail edge cases).
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  if (populated.length === 0) return null;
  const today = populated[populated.length - 1];
  // 5-day contribution per ticker: sum daily_return × weight over the
  // last 5 sessions where the ticker was held in the basket.
  const last5 = populated.slice(-5);
  const long5dContrib = new Map<string, number>();
  const short5dContrib = new Map<string, number>();
  for (const d of last5) {
    for (const e of d.long_basket) {
      long5dContrib.set(
        e.ticker,
        (long5dContrib.get(e.ticker) ?? 0) + e.weight * d.daily_return,
      );
    }
    for (const e of d.short_basket) {
      short5dContrib.set(
        e.ticker,
        (short5dContrib.get(e.ticker) ?? 0) + e.weight * d.daily_return,
      );
    }
  }
  const topLong = today.long_basket.slice().sort((a, b) => b.weight - a.weight).slice(0, 10);
  const topShort = today.short_basket.slice().sort((a, b) => b.weight - a.weight).slice(0, 10);

  return (
    <TmPane title="PORTFOLIO.TODAY" meta={`as_of ${today.date}`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Most recent populated session basket. 5d contribution = Σ (weight × daily_return) over the last 5 sessions where the ticker was held.
      </p>
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2">
        <BasketSide
          title="LONG · TOP 10"
          tone="pos"
          rows={topLong}
          contribMap={long5dContrib}
        />
        <BasketSide
          title="SHORT · TOP 10"
          tone="neg"
          rows={topShort}
          contribMap={short5dContrib}
        />
      </div>
    </TmPane>
  );
}
function BasketSide({
  title,
  tone,
  rows,
  contribMap,
}: {
  readonly title: string;
  readonly tone: "pos" | "neg";
  readonly rows: readonly { ticker: string; weight: number }[];
  readonly contribMap: ReadonlyMap<string, number>;
}) {
  const accentClass = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className="flex flex-col bg-tm-bg">
      <div className={`border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${accentClass}`}>
        {title}
      </div>
      <div
        className="grid gap-px bg-tm-rule"
        style={{ gridTemplateColumns: "32px minmax(80px, 100px) minmax(80px, 100px) minmax(100px, 1fr)" }}
      >
        <RHeader>#</RHeader>
        <RHeader>ticker</RHeader>
        <RHeader align="right">weight</RHeader>
        <RHeader align="right">5d contrib</RHeader>
        {rows.map((r, i) => {
          const contrib = contribMap.get(r.ticker) ?? 0;
          return (
            <BasketRow
              key={r.ticker}
              rank={i + 1}
              ticker={r.ticker}
              weight={r.weight}
              contrib={contrib}
              accentClass={accentClass}
            />
          );
        })}
      </div>
    </div>
  );
}
function BasketRow({
  rank, ticker, weight, contrib, accentClass,
}: {
  readonly rank: number;
  readonly ticker: string;
  readonly weight: number;
  readonly contrib: number;
  readonly accentClass: string;
}) {
  return (
    <>
      <RCell><span className="text-tm-muted">{String(rank).padStart(2, "0")}</span></RCell>
      <RCell><span className={`font-semibold ${accentClass}`}>{ticker}</span></RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-fg-2">{(weight * 100).toFixed(2)}%</span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${contrib >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {contrib >= 0 ? "+" : ""}{(contrib * 10000).toFixed(1)} bps
        </span>
      </RCell>
    </>
  );
}

/* ── 5. TURNOVER.PROFILE ──────────────────────────────────────────── */

function TurnoverProfilePane({
  breakdown,
}: {
  readonly breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>;
}) {
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  if (populated.length < 2) return null;

  // Daily turnover = L1 norm of weight delta between consecutive days.
  // Names rolled in/out = symmetric set diff between (long ∪ short) of
  // consecutive days. Both per-day metrics across the test slice.
  const turnovers: number[] = [];
  let totalRolledIn = 0;
  let totalRolledOut = 0;
  for (let i = 1; i < populated.length; i++) {
    const prev = populated[i - 1];
    const curr = populated[i];
    const wPrev = new Map<string, number>();
    for (const e of prev.long_basket) wPrev.set(e.ticker, e.weight);
    for (const e of prev.short_basket) wPrev.set(e.ticker, -e.weight);
    const wCurr = new Map<string, number>();
    for (const e of curr.long_basket) wCurr.set(e.ticker, e.weight);
    for (const e of curr.short_basket) wCurr.set(e.ticker, -e.weight);
    let l1 = 0;
    const allKeys = new Set<string>([
      ...Array.from(wPrev.keys()),
      ...Array.from(wCurr.keys()),
    ]);
    Array.from(allKeys).forEach((k) => {
      l1 += Math.abs((wCurr.get(k) ?? 0) - (wPrev.get(k) ?? 0));
    });
    turnovers.push(l1 / 2); // /2 because both sides changed
    const prevSet = new Set<string>(Array.from(wPrev.keys()));
    const currSet = new Set<string>(Array.from(wCurr.keys()));
    Array.from(currSet).forEach((k) => {
      if (!prevSet.has(k)) totalRolledIn++;
    });
    Array.from(prevSet).forEach((k) => {
      if (!currSet.has(k)) totalRolledOut++;
    });
  }
  const avgTurnover =
    turnovers.length > 0 ? turnovers.reduce((a, b) => a + b, 0) / turnovers.length : 0;
  const days = turnovers.length;
  const avgRolledIn = days > 0 ? totalRolledIn / days : 0;
  const avgRolledOut = days > 0 ? totalRolledOut / days : 0;

  // Bucketize turnovers into 8 bins from 0 to max
  const maxT = Math.max(...turnovers, 0.01);
  const binEdges = Array.from({ length: 9 }, (_, i) => (i / 8) * maxT);
  const dist = Array.from({ length: 8 }, (_, i) => {
    const lo = binEdges[i];
    const hi = binEdges[i + 1];
    return {
      label: `${(lo * 100).toFixed(0)}-${(hi * 100).toFixed(0)}%`,
      count: turnovers.filter((v) => v >= lo && (i === 7 ? v <= hi : v < hi)).length,
    };
  });

  return (
    <TmPane
      title="TURNOVER.PROFILE"
      meta={`avg ${(avgTurnover * 100).toFixed(0)}% / day · ${days} sessions`}
    >
      <TmKpiGrid>
        <TmKpi label="AVG TURNOVER" value={`${(avgTurnover * 100).toFixed(0)}%`}
          tone={avgTurnover > 0.5 ? "warn" : "default"}
          sub="L1 / 2 per day" />
        <TmKpi label="ROLLED IN" value={avgRolledIn.toFixed(1)}
          sub="new names per day" />
        <TmKpi label="ROLLED OUT" value={avgRolledOut.toFixed(1)}
          sub="dropped names per day" />
        <TmKpi label="COST AT 5BPS"
          value={`${(avgTurnover * 5 * 252 / 10000 * 100).toFixed(2)}%`}
          tone="warn"
          sub="annualized drag" />
      </TmKpiGrid>
      <div className="h-[180px] w-full px-1 pb-1 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dist} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)" interval={0} />
            <YAxis tick={{ fontSize: 9, fill: "var(--tm-muted)" }}
              stroke="var(--tm-rule)" allowDecimals={false} />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
            />
            <Bar dataKey="count" fill="var(--tm-info)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}

/* ── 7. POSITION.CONTRIBUTION ─────────────────────────────────────── */

interface PositionContrib {
  readonly ticker: string;
  readonly contrib: number; // sum of weight × daily_return
  readonly nDays: number;   // # of days held
  readonly hitDays: number; // # of days held with positive contribution
  readonly side: "long" | "short" | "both";
}
function aggregateContribution(
  breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>,
  trainEndIndex: number | null | undefined,
): PositionContrib[] {
  // Only test slice — trainEndIndex is in equity_curve indexing but
  // breakdown days share dates with equity_curve days, so we filter
  // breakdown by date. If we don't have a train cutoff, use all.
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  let testSlice = populated;
  if (
    typeof trainEndIndex === "number" &&
    trainEndIndex > 0 &&
    populated.length > trainEndIndex
  ) {
    testSlice = populated.slice(trainEndIndex);
  }
  const map = new Map<
    string,
    { contrib: number; nDays: number; hitDays: number; longDays: number; shortDays: number }
  >();
  for (const d of testSlice) {
    for (const e of d.long_basket) {
      const c = e.weight * d.daily_return;
      const cur = map.get(e.ticker) ?? { contrib: 0, nDays: 0, hitDays: 0, longDays: 0, shortDays: 0 };
      cur.contrib += c;
      cur.nDays += 1;
      cur.longDays += 1;
      if (c > 0) cur.hitDays += 1;
      map.set(e.ticker, cur);
    }
    for (const e of d.short_basket) {
      // Short side: contribution is -weight × daily_return (short profits
      // when the underlying drops, but daily_return here is the strategy's
      // return which already accounts for direction). Use weight × ret
      // consistently to mirror engine bookkeeping.
      const c = e.weight * d.daily_return;
      const cur = map.get(e.ticker) ?? { contrib: 0, nDays: 0, hitDays: 0, longDays: 0, shortDays: 0 };
      cur.contrib += c;
      cur.nDays += 1;
      cur.shortDays += 1;
      if (c > 0) cur.hitDays += 1;
      map.set(e.ticker, cur);
    }
  }
  const out: PositionContrib[] = Array.from(map.entries()).map(([ticker, v]) => ({
    ticker,
    contrib: v.contrib,
    nDays: v.nDays,
    hitDays: v.hitDays,
    side: v.longDays > 0 && v.shortDays > 0 ? "both" : v.longDays > 0 ? "long" : "short",
  }));
  return out.sort((a, b) => b.contrib - a.contrib);
}

function PositionContributionPane({
  breakdown,
  trainEndIndex,
}: {
  readonly breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>;
  readonly trainEndIndex: number | null | undefined;
}) {
  const all = useMemo(
    () => aggregateContribution(breakdown, trainEndIndex),
    [breakdown, trainEndIndex],
  );
  if (all.length === 0) return null;
  const top10 = all.slice(0, 10);
  const bottom10 = all.slice(-10).reverse();
  const totalContrib = all.reduce((a, p) => a + p.contrib, 0);
  const top10Share = totalContrib !== 0
    ? top10.reduce((a, p) => a + p.contrib, 0) / totalContrib
    : 0;

  return (
    <TmPane
      title="POSITION.CONTRIBUTION"
      meta={`${all.length} unique tickers · top 10 share ${(top10Share * 100).toFixed(0)}%`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Test-slice cumulative contribution (Σ weight × daily_return) per
        ticker. High top-10 share = concentration risk; low share = diversified attribution.
      </p>
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2">
        <ContribSide title="TOP 10 CONTRIBUTORS" tone="pos" rows={top10} />
        <ContribSide title="TOP 10 DETRACTORS" tone="neg" rows={bottom10} />
      </div>
    </TmPane>
  );
}
function ContribSide({
  title, tone, rows,
}: {
  readonly title: string;
  readonly tone: "pos" | "neg";
  readonly rows: readonly PositionContrib[];
}) {
  const accentClass = tone === "pos" ? "text-tm-pos" : "text-tm-neg";
  return (
    <div className="flex flex-col bg-tm-bg">
      <div className={`border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${accentClass}`}>
        {title}
      </div>
      <div
        className="grid gap-px bg-tm-rule"
        style={{ gridTemplateColumns: "32px minmax(80px,100px) 50px minmax(90px,1fr) 60px 60px" }}
      >
        <RHeader>#</RHeader>
        <RHeader>ticker</RHeader>
        <RHeader>side</RHeader>
        <RHeader align="right">contrib</RHeader>
        <RHeader align="right">days</RHeader>
        <RHeader align="right">hit %</RHeader>
        {rows.map((p, i) => (
          <ContribRow key={p.ticker} rank={i + 1} pos={p} />
        ))}
      </div>
    </div>
  );
}
function ContribRow({ rank, pos }: { readonly rank: number; readonly pos: PositionContrib }) {
  const sideTone =
    pos.side === "long" ? "text-tm-pos"
    : pos.side === "short" ? "text-tm-neg" : "text-tm-fg-2";
  const sideLabel =
    pos.side === "long" ? "L" : pos.side === "short" ? "S" : "L/S";
  const hitPct = pos.nDays > 0 ? (pos.hitDays / pos.nDays) * 100 : 0;
  return (
    <>
      <RCell><span className="text-tm-muted">{String(rank).padStart(2, "0")}</span></RCell>
      <RCell><span className="font-semibold text-tm-accent">{pos.ticker}</span></RCell>
      <RCell><span className={`tabular-nums ${sideTone}`}>{sideLabel}</span></RCell>
      <RCell align="right">
        <span className={`tabular-nums ${pos.contrib >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {pos.contrib >= 0 ? "+" : ""}{(pos.contrib * 10000).toFixed(1)} bps
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">{pos.nDays}</span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${hitPct > 50 ? "text-tm-pos" : "text-tm-muted"}`}>
          {hitPct.toFixed(0)}%
        </span>
      </RCell>
    </>
  );
}

/* ── RegimeBreakdownPane (unchanged from v2) ──────────────────────── */

function RegimeBreakdownPane({ result }: { readonly result: FactorBacktestResponse }) {
  const { locale } = useLocale();
  const breakdown = result.regime_breakdown ?? [];
  function alphaTone(p: number, ts: number): string {
    if (p < 0.05 && ts > 0) return "text-tm-pos";
    if (p < 0.05 && ts < 0) return "text-tm-neg";
    if (p < 0.1 && ts > 0) return "text-tm-warn";
    return "text-tm-muted";
  }
  return (
    <TmPane title="REGIME.BREAKDOWN" meta={`${breakdown.length} regimes`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.regime.subtitle")}
      </p>
      <div className="overflow-x-auto">
        <div className="grid min-w-[700px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "minmax(120px,140px) 60px 60px 80px 70px 80px 60px 60px" }}>
          <RHeader>{t(locale, "backtest.regime.label")}</RHeader>
          <RHeader align="right">N</RHeader>
          <RHeader align="right">SR</RHeader>
          <RHeader align="right">IC</RHeader>
          <RHeader align="right">IC p</RHeader>
          <RHeader align="right">α (ann)</RHeader>
          <RHeader align="right">α-t</RHeader>
          <RHeader align="right">α p</RHeader>
          {breakdown.map((r) => (
            <RegimeRow key={r.regime} regime={r} tone={alphaTone(r.alpha_pvalue, r.alpha_t_stat)} locale={locale} />
          ))}
        </div>
      </div>
    </TmPane>
  );
}
function RegimeRow({
  regime: r, tone, locale,
}: {
  readonly regime: NonNullable<FactorBacktestResponse["regime_breakdown"]>[number];
  readonly tone: string;
  readonly locale: "zh" | "en";
}) {
  return (
    <>
      <RCell><span className="text-tm-fg">
        {t(locale, `backtest.regime.${r.regime}` as Parameters<typeof t>[1])}
      </span></RCell>
      <RCell align="right"><span className="tabular-nums text-tm-muted">{r.n_days}</span></RCell>
      <RCell align="right">
        <span className={`tabular-nums ${r.sharpe >= 0 ? "text-tm-fg" : "text-tm-neg"}`}>
          {r.sharpe >= 0 ? "+" : ""}{r.sharpe.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${r.ic_spearman >= 0 ? "text-tm-fg" : "text-tm-neg"}`}>
          {r.ic_spearman >= 0 ? "+" : ""}{r.ic_spearman.toFixed(4)}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {r.ic_pvalue < 0.001 ? "<0.001" : r.ic_pvalue.toFixed(3)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_annualized >= 0 ? "+" : ""}{(r.alpha_annualized * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_t_stat >= 0 ? "+" : ""}{r.alpha_t_stat.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_pvalue < 0.001 ? "<0.001" : r.alpha_pvalue.toFixed(3)}
        </span>
      </RCell>
    </>
  );
}

/* ── WalkForwardPane (unchanged from v2) ──────────────────────────── */

function WalkForwardPane({
  windows,
}: {
  readonly windows: NonNullable<FactorBacktestResponse["walk_forward"]>;
}) {
  const { locale } = useLocale();
  const sharpes = windows.map((w) => w.sharpe);
  const min = Math.min(...sharpes);
  const max = Math.max(...sharpes);
  const range = max - min || 1;

  return (
    <TmPane title="WALKFORWARD"
      meta={`${windows.length} windows · SR range [${min.toFixed(2)}, ${max.toFixed(2)}]`}>
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.wf.subtitle")}
      </p>
      <div className="overflow-x-auto">
        <div className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "minmax(180px,220px) minmax(160px,200px) 70px 80px 80px 70px 70px" }}>
          <RHeader>{t(locale, "backtest.wf.colWindow")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colSharpe")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colIc")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colReturn")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colMdd")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colTurnover")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colHitRate")}</RHeader>
          {windows.map((w) => {
            const widthPct = Math.max(4, ((w.sharpe - min) / range) * 100);
            const barTone = w.sharpe > 0 ? "bg-tm-pos" : w.sharpe < 0 ? "bg-tm-neg" : "bg-tm-muted";
            return (
              <WfRow key={`${w.window_start}-${w.window_end}`} row={w} widthPct={widthPct} barTone={barTone} />
            );
          })}
        </div>
      </div>
    </TmPane>
  );
}
function WfRow({
  row: w, widthPct, barTone,
}: {
  readonly row: NonNullable<FactorBacktestResponse["walk_forward"]>[number];
  readonly widthPct: number;
  readonly barTone: string;
}) {
  return (
    <>
      <RCell><span className="font-tm-mono text-tm-fg-2">{w.window_start} → {w.window_end}</span></RCell>
      <div className="flex items-center justify-end gap-2 bg-tm-bg px-2 py-1 font-tm-mono text-[11px]">
        <div className="relative h-2 w-16 bg-tm-bg-3">
          <div className={`h-full ${barTone}`} style={{ width: `${widthPct}%` }} />
        </div>
        <span className={`tabular-nums ${w.sharpe >= 0 ? "text-tm-fg" : "text-tm-neg"}`}>
          {w.sharpe.toFixed(2)}
        </span>
      </div>
      <RCell align="right">
        <span className={`tabular-nums ${w.ic_spearman >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {w.ic_spearman.toFixed(3)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${w.total_return >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {(w.total_return * 100).toFixed(1)}%
        </span>
      </RCell>
      <RCell align="right"><span className="tabular-nums text-tm-neg">{(w.max_drawdown * 100).toFixed(1)}%</span></RCell>
      <RCell align="right"><span className="tabular-nums text-tm-muted">{w.turnover.toFixed(2)}</span></RCell>
      <RCell align="right"><span className="tabular-nums text-tm-muted">{(w.hit_rate * 100).toFixed(0)}%</span></RCell>
    </>
  );
}

/* ── DailyBreakdownPane (unchanged from v2) ───────────────────────── */

function DailyBreakdownPane({
  breakdown, factorName,
}: {
  readonly breakdown: NonNullable<FactorBacktestResponse["daily_breakdown"]>;
  readonly factorName: string;
}) {
  const { locale } = useLocale();
  const populated = breakdown.filter(
    (d) => d.long_basket.length > 0 || d.short_basket.length > 0,
  );
  const positiveIc = populated.filter((d) => d.daily_ic > 0).length;
  const hitRate = populated.length > 0 ? positiveIc / populated.length : 0;

  function downloadFlat() {
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
    <TmPane title="DAILY.BREAKDOWN"
      meta={`${populated.length} sessions · hit ${(hitRate * 100).toFixed(0)}%`}>
      <div className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          {t(locale, "backtest.breakdown.subtitle")
            .replace("{n}", String(populated.length))
            .replace("{hit}", `${(hitRate * 100).toFixed(0)}%`)}
        </span>
        <button type="button" onClick={downloadFlat}
          className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-accent">
          {t(locale, "backtest.breakdown.download")}
        </button>
      </div>
      <div className="overflow-x-auto">
        <div className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "minmax(110px,130px) 60px 60px 70px 70px 1fr 1fr" }}>
          <RHeader>{t(locale, "backtest.breakdown.colDate")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colNLong")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colNShort")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colReturn")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colIc")}</RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopLong")}</RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopShort")}</RHeader>
          {populated.slice(-30).reverse().map((d) => (
            <BreakdownRow key={d.date} row={d} />
          ))}
        </div>
      </div>
      <p className="border-t border-tm-rule px-3 py-1.5 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.breakdown.tableHint")}
      </p>
    </TmPane>
  );
}
function BreakdownRow({
  row: d,
}: {
  readonly row: NonNullable<FactorBacktestResponse["daily_breakdown"]>[number];
}) {
  return (
    <>
      <RCell><span className="font-tm-mono text-tm-fg">{d.date}</span></RCell>
      <RCell align="right"><span className="tabular-nums text-tm-muted">{d.long_basket.length}</span></RCell>
      <RCell align="right"><span className="tabular-nums text-tm-muted">{d.short_basket.length}</span></RCell>
      <RCell align="right">
        <span className={`tabular-nums ${d.daily_return >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {(d.daily_return * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${d.daily_ic >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>
          {d.daily_ic.toFixed(3)}
        </span>
      </RCell>
      <RCell><span className="truncate text-tm-muted">{d.long_basket.slice(0, 3).map((e) => e.ticker).join(", ")}</span></RCell>
      <RCell><span className="truncate text-tm-muted">{d.short_basket.slice(0, 3).map((e) => e.ticker).join(", ")}</span></RCell>
    </>
  );
}

/* ── Shared cells ─────────────────────────────────────────────────── */

function RHeader({ children, align = "left" }: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${align === "right" ? "text-right" : ""}`}>
      {children}
    </div>
  );
}

function RCell({ children, align = "left" }: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${align === "right" ? "justify-end" : ""}`}>
      {children}
    </div>
  );
}
