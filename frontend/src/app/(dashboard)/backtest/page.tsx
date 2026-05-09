"use client";

/**
 * Backtest page — workstation port (Stage 3 · 7/9, largest page).
 *
 * Layout: TmSubbar (factor + universe + status pills + run pulse) →
 *   BACKTEST.FORM → BACKTEST.KPI → RISK.ATTRIBUTION (4-cell α/β/R²/
 *   verdict) → REGIME.BREAKDOWN (conditional) → EQUITY.CURVE
 *   (FactorPnLChart inside TmPane) → DRAWDOWN.UNDERWATER →
 *   MONTHLY.RETURNS (conditional) → WALKFORWARD (conditional) →
 *   DAILY.BREAKDOWN (conditional with CSV export).
 *
 * Saving to Zoo lives in the subbar as a TmButton (was a separate Card
 * with right-aligned Button) so save state is always at hand.
 *
 * 4 new Tm* siblings created instead of in-place rewrites since
 * BacktestKpiStrip / DrawdownChart / MonthlyReturnsHeatmap are also
 * imported by /report (legacy until S3·8/9). Form is /backtest-only
 * so the legacy BacktestForm could be removed later, but keeping it
 * is a 1-file overhead and avoids touching working code.
 *
 * Behavior preserved byte-for-byte: PREFILL_KEY handoff, run + state
 * machine, ZooSaveButton args, equity_curve / benchmark_curve / regime
 * / walk_forward / daily_breakdown gating, CSV export.
 */

import { useEffect, useState } from "react";
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
import { TmDrawdownChart } from "@/components/backtest/TmDrawdownChart";
import { TmMonthlyReturnsHeatmap } from "@/components/backtest/TmMonthlyReturnsHeatmap";
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
          <TmStatusPill
            tone={result.survivorship_corrected ? "ok" : "warn"}
          >
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
          {result.regime_breakdown && result.regime_breakdown.length > 0 && (
            <RegimeBreakdownPane result={result} />
          )}
          <TmPane
            title="EQUITY.CURVE"
            meta={`${result.equity_curve.length} sessions · vs ${lastParams?.benchmarkTicker ?? "SPY"}`}
          >
            <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
              {t(locale, "backtest.equity.subtitle")}
            </p>
            <div className="px-2 pb-2 pt-2">
              <FactorPnLChart data={result} height={340} />
            </div>
          </TmPane>
          <TmDrawdownChart equityCurve={result.equity_curve} />
          {result.monthly_returns && result.monthly_returns.length > 0 && (
            <TmMonthlyReturnsHeatmap data={result.monthly_returns} />
          )}
          {result.walk_forward && result.walk_forward.length > 0 && (
            <WalkForwardPane windows={result.walk_forward} />
          )}
          {result.daily_breakdown && result.daily_breakdown.length > 0 && (
            <DailyBreakdownPane
              breakdown={result.daily_breakdown}
              factorName={result.factor_name}
            />
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

/* ── RiskAttributionPane ──────────────────────────────────────────── */

function RiskAttributionPane({
  result,
}: {
  readonly result: FactorBacktestResponse;
}) {
  const { locale } = useLocale();
  const alpha = result.alpha_annualized ?? 0;
  const beta = result.beta_market ?? 0;
  const r2 = result.r_squared ?? 0;
  const pAlpha = result.alpha_pvalue ?? 1;

  const alphaTone: "pos" | "neg" | "warn" | "default" =
    pAlpha < 0.05 && alpha > 0
      ? "pos"
      : pAlpha < 0.05 && alpha < 0
        ? "neg"
        : pAlpha < 0.1 && alpha > 0
          ? "warn"
          : "default";

  const verdict =
    pAlpha < 0.05 && Math.abs(beta) < 0.3
      ? t(locale, "backtest.risk.verdictAlphaPure")
      : pAlpha < 0.05
        ? t(locale, "backtest.risk.verdictAlphaLevered")
        : pAlpha < 0.1 && alpha > 0 && Math.abs(beta) < 0.3
          ? t(locale, "backtest.risk.verdictMarginal")
          : Math.abs(beta) > 0.5
            ? t(locale, "backtest.risk.verdictBetaOnly")
            : t(locale, "backtest.risk.verdictNoise");

  const betaTone: "warn" | "default" =
    Math.abs(beta) > 0.5 ? "warn" : "default";

  return (
    <TmPane title="RISK.ATTRIBUTION" meta="α / β / R² / verdict">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.risk.subtitle")}
      </p>
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "backtest.risk.alpha")}
          value={`${alpha >= 0 ? "+" : ""}${(alpha * 100).toFixed(2)}%`}
          tone={alphaTone}
          sub={`p=${pAlpha < 0.001 ? "<0.001" : pAlpha.toFixed(3)}`}
        />
        <TmKpi
          label={t(locale, "backtest.risk.beta")}
          value={`${beta >= 0 ? "+" : ""}${beta.toFixed(3)}`}
          tone={betaTone}
          sub={t(locale, "backtest.risk.betaHint")}
        />
        <TmKpi
          label="R²"
          value={`${(r2 * 100).toFixed(1)}%`}
          sub={t(locale, "backtest.risk.r2Hint")}
        />
        <TmKpi
          label={t(locale, "backtest.risk.verdict")}
          value={verdict}
          tone={alphaTone}
        />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── RegimeBreakdownPane ──────────────────────────────────────────── */

function RegimeBreakdownPane({
  result,
}: {
  readonly result: FactorBacktestResponse;
}) {
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
        <div
          className="grid min-w-[700px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(120px, 140px) 60px 60px 80px 70px 80px 60px 60px",
          }}
        >
          <RHeader>{t(locale, "backtest.regime.label")}</RHeader>
          <RHeader align="right">N</RHeader>
          <RHeader align="right">SR</RHeader>
          <RHeader align="right">IC</RHeader>
          <RHeader align="right">IC p</RHeader>
          <RHeader align="right">α (ann)</RHeader>
          <RHeader align="right">α-t</RHeader>
          <RHeader align="right">α p</RHeader>
          {breakdown.map((r) => {
            const tone = alphaTone(r.alpha_pvalue, r.alpha_t_stat);
            return (
              <RegimeRow key={r.regime} regime={r} tone={tone} locale={locale} />
            );
          })}
        </div>
      </div>
    </TmPane>
  );
}

function RegimeRow({
  regime: r,
  tone,
  locale,
}: {
  readonly regime: NonNullable<FactorBacktestResponse["regime_breakdown"]>[number];
  readonly tone: string;
  readonly locale: "zh" | "en";
}) {
  return (
    <>
      <RCell>
        <span className="text-tm-fg">
          {t(locale, `backtest.regime.${r.regime}` as Parameters<typeof t>[1])}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">{r.n_days}</span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${r.sharpe >= 0 ? "text-tm-fg" : "text-tm-neg"}`}
        >
          {r.sharpe >= 0 ? "+" : ""}
          {r.sharpe.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${r.ic_spearman >= 0 ? "text-tm-fg" : "text-tm-neg"}`}
        >
          {r.ic_spearman >= 0 ? "+" : ""}
          {r.ic_spearman.toFixed(4)}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {r.ic_pvalue < 0.001 ? "<0.001" : r.ic_pvalue.toFixed(3)}
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_annualized >= 0 ? "+" : ""}
          {(r.alpha_annualized * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className={`tabular-nums ${tone}`}>
          {r.alpha_t_stat >= 0 ? "+" : ""}
          {r.alpha_t_stat.toFixed(2)}
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

/* ── WalkForwardPane ──────────────────────────────────────────────── */

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
    <TmPane
      title="WALKFORWARD"
      meta={`${windows.length} windows · SR range [${min.toFixed(2)}, ${max.toFixed(2)}]`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.wf.subtitle")}
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(180px, 220px) minmax(160px, 200px) 70px 80px 80px 70px 70px",
          }}
        >
          <RHeader>{t(locale, "backtest.wf.colWindow")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colSharpe")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colIc")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colReturn")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colMdd")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colTurnover")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.wf.colHitRate")}</RHeader>
          {windows.map((w) => {
            const widthPct = Math.max(4, ((w.sharpe - min) / range) * 100);
            const barTone =
              w.sharpe > 0 ? "bg-tm-pos" : w.sharpe < 0 ? "bg-tm-neg" : "bg-tm-muted";
            return (
              <RegimeWfRow
                key={`${w.window_start}-${w.window_end}`}
                row={w}
                widthPct={widthPct}
                barTone={barTone}
              />
            );
          })}
        </div>
      </div>
    </TmPane>
  );
}

function RegimeWfRow({
  row: w,
  widthPct,
  barTone,
}: {
  readonly row: NonNullable<FactorBacktestResponse["walk_forward"]>[number];
  readonly widthPct: number;
  readonly barTone: string;
}) {
  return (
    <>
      <RCell>
        <span className="font-tm-mono text-tm-fg-2">
          {w.window_start} → {w.window_end}
        </span>
      </RCell>
      <div className="flex items-center justify-end gap-2 bg-tm-bg px-2 py-1 font-tm-mono text-[11px]">
        <div className="relative h-2 w-16 bg-tm-bg-3">
          <div
            className={`h-full ${barTone}`}
            style={{ width: `${widthPct}%` }}
          />
        </div>
        <span
          className={`tabular-nums ${w.sharpe >= 0 ? "text-tm-fg" : "text-tm-neg"}`}
        >
          {w.sharpe.toFixed(2)}
        </span>
      </div>
      <RCell align="right">
        <span
          className={`tabular-nums ${w.ic_spearman >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {w.ic_spearman.toFixed(3)}
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${w.total_return >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {(w.total_return * 100).toFixed(1)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-neg">
          {(w.max_drawdown * 100).toFixed(1)}%
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {w.turnover.toFixed(2)}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {(w.hit_rate * 100).toFixed(0)}%
        </span>
      </RCell>
    </>
  );
}

/* ── DailyBreakdownPane ───────────────────────────────────────────── */

function DailyBreakdownPane({
  breakdown,
  factorName,
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
        rows.push([
          d.date,
          "long",
          e.ticker,
          e.weight.toFixed(6),
          d.daily_return.toFixed(6),
          d.daily_ic.toFixed(6),
        ]);
      }
      for (const e of d.short_basket) {
        rows.push([
          d.date,
          "short",
          e.ticker,
          e.weight.toFixed(6),
          d.daily_return.toFixed(6),
          d.daily_ic.toFixed(6),
        ]);
      }
    }
    const csv = rows
      .map((r) => r.map((c) => `"${c.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${factorName}_daily_breakdown.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <TmPane
      title="DAILY.BREAKDOWN"
      meta={`${populated.length} sessions · hit ${(hitRate * 100).toFixed(0)}%`}
    >
      <div className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          {t(locale, "backtest.breakdown.subtitle")
            .replace("{n}", String(populated.length))
            .replace("{hit}", `${(hitRate * 100).toFixed(0)}%`)}
        </span>
        <button
          type="button"
          onClick={downloadFlat}
          className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-accent"
        >
          {t(locale, "backtest.breakdown.download")}
        </button>
      </div>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(110px, 130px) 60px 60px 70px 70px 1fr 1fr",
          }}
        >
          <RHeader>{t(locale, "backtest.breakdown.colDate")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colNLong")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colNShort")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colReturn")}</RHeader>
          <RHeader align="right">{t(locale, "backtest.breakdown.colIc")}</RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopLong")}</RHeader>
          <RHeader>{t(locale, "backtest.breakdown.colTopShort")}</RHeader>
          {populated
            .slice(-30)
            .reverse()
            .map((d) => (
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
      <RCell>
        <span className="font-tm-mono text-tm-fg">{d.date}</span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {d.long_basket.length}
        </span>
      </RCell>
      <RCell align="right">
        <span className="tabular-nums text-tm-muted">
          {d.short_basket.length}
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${d.daily_return >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {(d.daily_return * 100).toFixed(2)}%
        </span>
      </RCell>
      <RCell align="right">
        <span
          className={`tabular-nums ${d.daily_ic >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
        >
          {d.daily_ic.toFixed(3)}
        </span>
      </RCell>
      <RCell>
        <span className="truncate text-tm-muted">
          {d.long_basket
            .slice(0, 3)
            .map((e) => e.ticker)
            .join(", ")}
        </span>
      </RCell>
      <RCell>
        <span className="truncate text-tm-muted">
          {d.short_basket
            .slice(0, 3)
            .map((e) => e.ticker)
            .join(", ")}
        </span>
      </RCell>
    </>
  );
}

/* ── Shared cells ─────────────────────────────────────────────────── */

function RHeader({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function RCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
    >
      {children}
    </div>
  );
}
