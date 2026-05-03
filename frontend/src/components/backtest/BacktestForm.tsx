"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Slider } from "@/components/ui/Slider";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FACTOR_EXAMPLES, type FactorExample } from "@/components/alpha/FactorExamples";
import { extractOps } from "@/lib/factor-spec";
import type { BacktestDirection, BacktestMode } from "@/lib/types";

export interface BacktestFormParams {
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly direction: BacktestDirection;
  readonly trainRatio: number;
  readonly topPct: number;          // 1-50
  readonly bottomPct: number;       // 1-50
  readonly transactionCostBps: number;  // 0-50
  readonly mode: BacktestMode;
  readonly wfWindowDays: number;    // 20-252
  readonly wfStepDays: number;      // 5-wfWindowDays
  readonly includeBreakdown: boolean;
  readonly maskEarningsWindow: boolean;
  readonly neutralize: "none" | "sector";  // Bundle A.2 v4
  readonly benchmarkTicker: "SPY" | "RSP";  // v4 alternative benchmark
}

interface BacktestFormProps {
  readonly running: boolean;
  readonly onRun: (p: BacktestFormParams) => void;
  readonly initialExpression?: string;
  readonly autoRun?: boolean;
  // v4 cross-page parity: when /factors Zoo replays an entry, the saved
  // config flows in as initialConfig so the form reproduces the EXACT
  // backtest. All fields optional — undefined falls back to platform
  // defaults defined inline below.
  readonly initialConfig?: {
    readonly direction?: BacktestDirection;
    readonly neutralize?: "none" | "sector";
    readonly benchmarkTicker?: "SPY" | "RSP";
    readonly mode?: BacktestMode;
    readonly topPct?: number;
    readonly bottomPct?: number;
    readonly transactionCostBps?: number;
  };
}

const DIRECTIONS: readonly BacktestDirection[] = ["long_only", "long_short", "short_only"];
const MODES: readonly BacktestMode[] = ["static", "walk_forward"];

export function BacktestForm({
  running, onRun, initialExpression, autoRun, initialConfig,
}: BacktestFormProps) {
  const { locale } = useLocale();
  const [expr, setExpr] = useState(initialExpression ?? "rank(ts_mean(returns, 12))");
  const [direction, setDirection] = useState<BacktestDirection>(
    initialConfig?.direction ?? "long_short",
  );
  const [trainRatio, setTrainRatio] = useState(70);   // 0.10–0.95 stored as %
  const [topPct, setTopPct] = useState(
    initialConfig?.topPct !== undefined ? Math.round(initialConfig.topPct * 100) : 30,
  );
  const [bottomPct, setBottomPct] = useState(
    initialConfig?.bottomPct !== undefined ? Math.round(initialConfig.bottomPct * 100) : 30,
  );
  const [costBps, setCostBps] = useState(initialConfig?.transactionCostBps ?? 0);
  const [mode, setMode] = useState<BacktestMode>(initialConfig?.mode ?? "static");
  const [wfWindowDays, setWfWindowDays] = useState(60);
  const [wfStepDays, setWfStepDays] = useState(20);
  const [includeBreakdown, setIncludeBreakdown] = useState(false);
  const [maskEarningsWindow, setMaskEarningsWindow] = useState(false);
  const [neutralize, setNeutralize] = useState<"none" | "sector">(
    initialConfig?.neutralize ?? "none",
  );
  const [benchmarkTicker, setBenchmarkTicker] = useState<"SPY" | "RSP">(
    initialConfig?.benchmarkTicker ?? "SPY",
  );

  // P6.D — when /alpha hands off via sessionStorage and the page passes
  // autoRun, fire the run once on first mount so the user lands on a
  // populated dashboard without having to click "运行回测" again.
  useEffect(() => {
    if (autoRun && initialExpression) {
      onRun({
        expression: initialExpression,
        operators_used: [...extractOps(initialExpression)],
        lookback: 12,
        direction: "long_short",
        trainRatio: 0.7,
        topPct: 0.3,
        bottomPct: 0.3,
        transactionCostBps: 0,
        mode: "static",
        wfWindowDays: 60,
        wfStepDays: 20,
        includeBreakdown: false,
        maskEarningsWindow: false,
        neutralize: "none",
        benchmarkTicker: "SPY",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadExample(ex: FactorExample) {
    setExpr(ex.expression);
  }

  function submit() {
    onRun({
      expression: expr.trim(),
      operators_used: [...extractOps(expr)],
      lookback: 12,
      direction,
      trainRatio: trainRatio / 100,
      topPct: topPct / 100,
      bottomPct: bottomPct / 100,
      transactionCostBps: costBps,
      mode,
      // Clamp wfStepDays so it never exceeds wfWindowDays (backend validates)
      wfWindowDays,
      wfStepDays: Math.min(wfStepDays, wfWindowDays),
      includeBreakdown,
      maskEarningsWindow,
      neutralize,
      benchmarkTicker,
    });
  }

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "backtest.form.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
          {t(locale, "backtest.form.subtitle")}
        </p>
      </header>

      <textarea
        value={expr}
        onChange={(e) => setExpr(e.target.value)}
        placeholder={t(locale, "backtest.form.exprPlaceholder")}
        rows={3}
        className="w-full resize-none rounded-md border border-border bg-[var(--toggle-bg)] p-2 font-mono text-sm text-text outline-none focus:border-accent"
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-muted">{t(locale, "backtest.form.direction")}:</span>
        {DIRECTIONS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDirection(d)}
            className={
              direction === d
                ? "rounded-md bg-accent/15 px-2 py-1 font-mono text-[12px] text-accent"
                : "rounded-md px-2 py-1 font-mono text-[12px] text-muted hover:bg-[var(--toggle-bg)] hover:text-text"
            }
          >
            {d.replace("_", " ")}
          </button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Slider
          label={t(locale, "backtest.form.trainRatio")}
          min={50} max={90} step={5}
          value={trainRatio} onChange={setTrainRatio} unit="%"
        />
        <Slider
          label={t(locale, "backtest.form.topPct")}
          min={5} max={50} step={5}
          value={topPct} onChange={setTopPct} unit="%"
        />
        <Slider
          label={t(locale, "backtest.form.bottomPct")}
          min={5} max={50} step={5}
          value={bottomPct} onChange={setBottomPct} unit="%"
        />
        <Slider
          label={t(locale, "backtest.form.costBps")}
          min={0} max={50} step={1}
          value={costBps} onChange={setCostBps} unit="bps"
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-muted">
          {t(locale, "backtest.form.modeLabel")}:
        </span>
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={
              mode === m
                ? "rounded-md bg-accent/15 px-2 py-1 font-mono text-[12px] text-accent"
                : "rounded-md px-2 py-1 font-mono text-[12px] text-muted hover:bg-[var(--toggle-bg)] hover:text-text"
            }
          >
            {t(locale, m === "static" ? "backtest.form.modeStatic" : "backtest.form.modeWalkForward")}
          </button>
        ))}
        {mode === "walk_forward" && (
          <span className="ml-2 text-[12px] text-muted">
            {t(locale, "backtest.form.modeWfHelp")}
          </span>
        )}
      </div>

      {mode === "walk_forward" && (
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Slider
            label={t(locale, "backtest.form.wfWindow")}
            min={20} max={252} step={10}
            value={wfWindowDays} onChange={setWfWindowDays} unit="d"
          />
          <Slider
            label={t(locale, "backtest.form.wfStep")}
            min={5} max={Math.min(wfWindowDays, 60)} step={5}
            value={wfStepDays} onChange={setWfStepDays} unit="d"
          />
        </div>
      )}

      <label className="mt-3 flex items-center gap-2 text-[13px] text-muted">
        <input
          type="checkbox"
          checked={includeBreakdown}
          onChange={(e) => setIncludeBreakdown(e.target.checked)}
          className="cursor-pointer"
        />
        <span>{t(locale, "backtest.form.includeBreakdown")}</span>
        <span className="text-[12px] text-muted">
          {t(locale, "backtest.form.includeBreakdownHint")}
        </span>
      </label>

      <label className="mt-2 flex items-center gap-2 text-[13px] text-muted">
        <input
          type="checkbox"
          checked={maskEarningsWindow}
          onChange={(e) => setMaskEarningsWindow(e.target.checked)}
          className="cursor-pointer"
        />
        <span>{t(locale, "backtest.form.maskEarnings")}</span>
        <span className="text-[12px] text-muted">
          {t(locale, "backtest.form.maskEarningsHint")}
        </span>
      </label>

      <div className="mt-2 flex items-center gap-2 text-[13px] text-muted">
        <span>{t(locale, "backtest.form.neutralize")}:</span>
        {(["none", "sector"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setNeutralize(mode)}
            className={`rounded px-2 py-0.5 text-[12px] ${
              neutralize === mode
                ? "bg-accent text-white"
                : "bg-[var(--toggle-bg)] text-muted hover:text-text"
            }`}
          >
            {t(locale, `backtest.form.neutralize.${mode}`)}
          </button>
        ))}
        <span className="text-[12px] text-muted">
          {t(locale, "backtest.form.neutralizeHint")}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-[13px] text-muted">
        <span>{t(locale, "backtest.form.benchmark")}:</span>
        {(["SPY", "RSP"] as const).map((bt) => (
          <button
            key={bt}
            type="button"
            onClick={() => setBenchmarkTicker(bt)}
            className={`rounded px-2 py-0.5 text-[12px] font-mono ${
              benchmarkTicker === bt
                ? "bg-accent text-white"
                : "bg-[var(--toggle-bg)] text-muted hover:text-text"
            }`}
          >
            {bt}
          </button>
        ))}
        <span className="text-[12px] text-muted">
          {t(locale, "backtest.form.benchmarkHint")}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <details className="flex-1">
          <summary className="cursor-pointer text-[13px] text-muted hover:text-text">
            {t(locale, "backtest.form.loadExample")}
          </summary>
          <div className="mt-2 flex flex-wrap gap-1">
            {FACTOR_EXAMPLES.map((ex) => (
              <button
                key={ex.name}
                type="button"
                onClick={() => loadExample(ex)}
                className="rounded bg-[var(--toggle-bg)] px-2 py-1 text-[12px] text-muted hover:text-text"
              >
                {ex.name}
              </button>
            ))}
          </div>
        </details>
        <Button onClick={submit} disabled={running || expr.trim().length === 0}>
          {running ? t(locale, "backtest.form.running") : t(locale, "backtest.form.run")}
        </Button>
      </div>
    </Card>
  );
}
