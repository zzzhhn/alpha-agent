"use client";

/**
 * TmBacktestForm — workstation port of BacktestForm.
 *
 * Layout: textarea for expression, then chip rows for direction +
 * mode + neutralize + benchmark, then 4-cell slider grid (train ratio
 * / top % / bottom % / cost bps), conditional walk-forward sliders,
 * 2 toggles (include_breakdown / mask_earnings), factor-examples chip
 * row, run button.
 *
 * Auto-run + initialConfig prefill semantics preserved byte-for-byte
 * from legacy form so /factors → /backtest replay still reproduces
 * the exact saved-headline backtest config.
 */

import { useEffect, useState, type ChangeEvent } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton } from "@/components/tm/TmButton";
import { TmChip } from "@/components/tm/TmSubbar";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { extractOps } from "@/lib/factor-spec";
import type { BacktestDirection, BacktestMode } from "@/lib/types";

export interface BacktestFormParams {
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly direction: BacktestDirection;
  readonly trainRatio: number;
  readonly topPct: number;
  readonly bottomPct: number;
  readonly transactionCostBps: number;
  readonly mode: BacktestMode;
  readonly wfWindowDays: number;
  readonly wfStepDays: number;
  readonly includeBreakdown: boolean;
  readonly maskEarningsWindow: boolean;
  readonly neutralize: "none" | "sector";
  readonly benchmarkTicker: "SPY" | "RSP";
}

interface TmBacktestFormProps {
  readonly running: boolean;
  readonly onRun: (p: BacktestFormParams) => void;
  readonly initialExpression?: string;
  readonly autoRun?: boolean;
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

const DIRECTIONS: readonly BacktestDirection[] = [
  "long_only",
  "long_short",
  "short_only",
];
const MODES: readonly BacktestMode[] = ["static", "walk_forward"];

export function TmBacktestForm({
  running,
  onRun,
  initialExpression,
  autoRun,
  initialConfig,
}: TmBacktestFormProps) {
  const { locale } = useLocale();
  const [expr, setExpr] = useState(
    initialExpression ?? "rank(ts_mean(returns, 12))",
  );
  const [direction, setDirection] = useState<BacktestDirection>(
    initialConfig?.direction ?? "long_short",
  );
  const [trainRatio, setTrainRatio] = useState(70);
  const [topPct, setTopPct] = useState(
    initialConfig?.topPct !== undefined
      ? Math.round(initialConfig.topPct * 100)
      : 30,
  );
  const [bottomPct, setBottomPct] = useState(
    initialConfig?.bottomPct !== undefined
      ? Math.round(initialConfig.bottomPct * 100)
      : 30,
  );
  const [costBps, setCostBps] = useState(
    initialConfig?.transactionCostBps ?? 0,
  );
  const [mode, setMode] = useState<BacktestMode>(
    initialConfig?.mode ?? "static",
  );
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

  // P6.D auto-run on /alpha handoff — reproduces legacy default config
  // since the handoff passes only expression (legacy preserved).
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
      wfWindowDays,
      wfStepDays: Math.min(wfStepDays, wfWindowDays),
      includeBreakdown,
      maskEarningsWindow,
      neutralize,
      benchmarkTicker,
    });
  }

  return (
    <TmPane
      title="BACKTEST.FORM"
      meta={`${expr.length} CHARS · ${direction} · ${mode}`}
    >
      <div className="flex flex-col gap-3 px-3 py-3">
        <textarea
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder={t(locale, "backtest.form.exprPlaceholder")}
          rows={3}
          spellCheck={false}
          className="w-full resize-none border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg outline-none transition-colors focus:border-tm-accent"
        />

        {/* Direction + Mode + Neutralize + Benchmark — 4 chip rows */}
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <ChipGroup
            label={t(locale, "backtest.form.direction")}
            options={DIRECTIONS.map((d) => ({
              code: d,
              label: d.replace("_", " "),
            }))}
            value={direction}
            onChange={(v) => setDirection(v as BacktestDirection)}
          />
          <ChipGroup
            label={t(locale, "backtest.form.modeLabel")}
            options={MODES.map((m) => ({
              code: m,
              label: t(
                locale,
                m === "static"
                  ? "backtest.form.modeStatic"
                  : "backtest.form.modeWalkForward",
              ),
            }))}
            value={mode}
            onChange={(v) => setMode(v as BacktestMode)}
          />
          <ChipGroup
            label={t(locale, "backtest.form.neutralize")}
            options={[
              { code: "none", label: t(locale, "backtest.form.neutralize.none") },
              {
                code: "sector",
                label: t(locale, "backtest.form.neutralize.sector"),
              },
            ]}
            value={neutralize}
            onChange={(v) => setNeutralize(v as "none" | "sector")}
            hint={t(locale, "backtest.form.neutralizeHint")}
          />
          <ChipGroup
            label={t(locale, "backtest.form.benchmark")}
            options={[
              { code: "SPY", label: "SPY" },
              { code: "RSP", label: "RSP" },
            ]}
            value={benchmarkTicker}
            onChange={(v) => setBenchmarkTicker(v as "SPY" | "RSP")}
            hint={t(locale, "backtest.form.benchmarkHint")}
          />
        </div>

        {/* 4 sliders — train ratio / top% / bottom% / cost bps */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
          <TmSlider
            label={t(locale, "backtest.form.trainRatio")}
            min={50}
            max={90}
            step={5}
            value={trainRatio}
            unit="%"
            onChange={setTrainRatio}
          />
          <TmSlider
            label={t(locale, "backtest.form.topPct")}
            min={5}
            max={50}
            step={5}
            value={topPct}
            unit="%"
            onChange={setTopPct}
          />
          <TmSlider
            label={t(locale, "backtest.form.bottomPct")}
            min={5}
            max={50}
            step={5}
            value={bottomPct}
            unit="%"
            onChange={setBottomPct}
          />
          <TmSlider
            label={t(locale, "backtest.form.costBps")}
            min={0}
            max={50}
            step={1}
            value={costBps}
            unit="bps"
            onChange={setCostBps}
          />
        </div>

        {/* Walk-forward sliders, conditional */}
        {mode === "walk_forward" && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <TmSlider
              label={t(locale, "backtest.form.wfWindow")}
              min={20}
              max={252}
              step={10}
              value={wfWindowDays}
              unit="d"
              onChange={setWfWindowDays}
            />
            <TmSlider
              label={t(locale, "backtest.form.wfStep")}
              min={5}
              max={Math.min(wfWindowDays, 60)}
              step={5}
              value={wfStepDays}
              unit="d"
              onChange={setWfStepDays}
            />
          </div>
        )}

        {/* Toggles */}
        <div className="flex flex-col gap-1.5">
          <label className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg">
            <input
              type="checkbox"
              checked={includeBreakdown}
              onChange={(e) => setIncludeBreakdown(e.target.checked)}
              className="cursor-pointer accent-[var(--tm-accent)]"
            />
            <span>{t(locale, "backtest.form.includeBreakdown")}</span>
            <span className="text-[10.5px] text-tm-muted">
              {t(locale, "backtest.form.includeBreakdownHint")}
            </span>
          </label>
          <label className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg">
            <input
              type="checkbox"
              checked={maskEarningsWindow}
              onChange={(e) => setMaskEarningsWindow(e.target.checked)}
              className="cursor-pointer accent-[var(--tm-accent)]"
            />
            <span>{t(locale, "backtest.form.maskEarnings")}</span>
            <span className="text-[10.5px] text-tm-muted">
              {t(locale, "backtest.form.maskEarningsHint")}
            </span>
          </label>
        </div>

        {/* Footer: examples + run button */}
        <div className="flex flex-wrap items-end justify-between gap-3 border-t border-tm-rule pt-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "backtest.form.loadExample")}
            </span>
            {FACTOR_EXAMPLES.map((ex) => (
              <TmChip key={ex.name} onClick={() => loadExample(ex)}>
                {ex.name}
              </TmChip>
            ))}
          </div>
          <TmButton
            variant="primary"
            onClick={submit}
            disabled={running || expr.trim().length === 0}
          >
            {running
              ? t(locale, "backtest.form.running")
              : t(locale, "backtest.form.run")}
          </TmButton>
        </div>
      </div>
    </TmPane>
  );
}

/* ── ChipGroup ────────────────────────────────────────────────────── */

function ChipGroup({
  label,
  options,
  value,
  onChange,
  hint,
}: {
  readonly label: string;
  readonly options: readonly { code: string; label: string }[];
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-1.5">
        {options.map((o) => (
          <TmChip
            key={o.code}
            on={value === o.code}
            onClick={() => onChange(o.code)}
          >
            {o.label}
          </TmChip>
        ))}
        {hint && (
          <span className="ml-1 font-tm-mono text-[10px] text-tm-muted">
            {hint}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Slider primitive ─────────────────────────────────────────────── */

function TmSlider({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
}: {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly unit?: string;
  readonly onChange: (n: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between font-tm-mono">
        <label className="text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
          {label}
        </label>
        <span className="text-[12px] tabular-nums text-tm-fg">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(Number(e.target.value))
        }
        className="h-1 w-full accent-[var(--tm-accent)]"
      />
    </div>
  );
}
