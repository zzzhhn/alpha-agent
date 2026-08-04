"use client";

import {
  AlertCircle,
  Bookmark,
  Loader2,
  Star,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { parseFactorError } from "@/lib/factor-errors";
import { BacktestVerdictHeadline } from "./BacktestVerdictHeadline";
import { DecisionStrip } from "@/components/workbench/DecisionStrip";
import type {
  MetricDelta,
  Run,
  RunDeltas,
  RunState,
} from "./types";

/**
 * Thresholds prop shape — narrowed equivalent of `useBacktestSession()`'s
 * THRESHOLDS const. Kept as a structural interface so consumers can pass
 * either the hook's `as const` literal or a hand-built object without TS
 * variance gymnastics. All values are raw fractions (e.g. -0.15 = -15%).
 */
export interface VerdictThresholds {
  readonly sharpe: number;
  readonly sharpeWarn: number;
  readonly maxDD: number;
  readonly maxDDBad: number;
  readonly ic: number;
  readonly turnover: number;
  readonly turnoverBad: number;
  readonly annReturn: number;
}

interface BacktestVerdictBarProps {
  readonly runState: RunState;
  readonly currentRun: Run | null;
  readonly deltas: RunDeltas;
  readonly thresholds: VerdictThresholds;
  readonly baselineRunId: string | null;
  readonly recentRunsCount: number;
  readonly onSaveToZoo: () => void;
  readonly onTogglePin: () => void;
  readonly onReRun: () => void;
}

type TrafficLight = "ok" | "warn" | "bad";

function decisionTone(light: TrafficLight | null): "default" | "positive" | "warning" | "negative" {
  if (light === "ok") return "positive";
  if (light === "warn") return "warning";
  if (light === "bad") return "negative";
  return "default";
}

/* ---------- Threshold classifiers (per spec §8.2) ---------- */

function classifySharpe(v: number, th: VerdictThresholds): TrafficLight {
  if (v >= th.sharpe) return "ok";
  if (v >= th.sharpeWarn) return "warn";
  return "bad";
}

function classifyMaxDD(v: number, th: VerdictThresholds): TrafficLight {
  // maxDD is negative; closer to 0 is better.
  if (v >= th.maxDD) return "ok";
  if (v >= th.maxDDBad) return "warn";
  return "bad";
}

function classifyIC(v: number, th: VerdictThresholds): TrafficLight {
  if (v >= th.ic) return "ok";
  if (v >= 0) return "warn";
  return "bad";
}

function classifyTurnover(v: number, th: VerdictThresholds): TrafficLight {
  // LOWER IS BETTER.
  if (v <= th.turnover) return "ok";
  if (v <= th.turnoverBad) return "warn";
  return "bad";
}

function classifyAnnReturn(v: number, th: VerdictThresholds): TrafficLight {
  if (v >= th.annReturn) return "ok";
  if (v >= 0) return "warn";
  return "bad";
}

/* ---------- Value formatters ---------- */

function fmtSharpe(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

function fmtMaxDD(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function fmtIC(v: number | null): string {
  return v === null ? "—" : v.toFixed(4);
}

function fmtTurnover(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

function fmtAnnReturn(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

/* ---------- Delta diff formatters (signed) ---------- */

function fmtDeltaSharpe(diff: number): string {
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff.toFixed(2)}`;
}

function fmtDeltaPercentage1dp(diff: number): string {
  const pct = diff * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function fmtDeltaPercentage0dp(diff: number): string {
  const pct = diff * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(0)}%`;
}

function fmtDeltaIC(diff: number): string {
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff.toFixed(4)}`;
}

/* ---------- Main component ---------- */

export function BacktestVerdictBar({
  runState,
  currentRun,
  deltas,
  thresholds,
  baselineRunId,
  recentRunsCount,
  onSaveToZoo,
  onTogglePin,
  onReRun,
}: BacktestVerdictBarProps) {
  const { locale } = useLocale();

  // 1. idle
  if (runState.kind === "idle") {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm text-tm-muted">
        {t(locale, "backtest.verdict.idle")}
      </section>
    );
  }

  // 2. running — spinner + ETA copy (spec §8.2). Per task brief option (b),
  // replace metrics with the spinner regardless of stale currentRun.
  if (runState.kind === "running") {
    return (
      <section className="flex items-center gap-2 rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm text-tm-fg-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
        <span>{t(locale, "backtest.verdict.running")}</span>
      </section>
    );
  }

  // 3. error — red bar with parsed summary + optional collapsible detail
  //    + Re-run. Full raw message is gated behind <details> so the page no
  //    longer dumps the FastAPI 422 whitelist on first paint.
  if (runState.kind === "error") {
    const parsed = parseFactorError(runState.message);
    const isUnknownOperator =
      parsed.kind === "validation" &&
      !!parsed.badField &&
      parsed.badField.startsWith("operators_used") &&
      !!parsed.badValue;
    const isUnknownOperand =
      parsed.kind === "validation" &&
      parsed.badField === "expression.operand" &&
      !!parsed.badValue;
    const headline = isUnknownOperator
      ? `${t(locale, "backtest.verdict.unknownOp")}: ${parsed.badValue}`
      : isUnknownOperand
      ? `${t(locale, "backtest.verdict.unknownOperand")}: ${parsed.badValue}`
      : parsed.summary;
    const showDetail = parsed.detail !== null && parsed.detail !== parsed.summary;
    return (
      <section className="flex flex-col gap-2 rounded border border-tm-neg/40 bg-tm-neg/10 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-2 font-tm-mono text-sm text-tm-neg">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
            <span className="break-words">
              {t(locale, "backtest.verdict.errorPrefix")}
              {headline}
            </span>
          </div>
          <button
            type="button"
            onClick={onReRun}
            className="rounded border border-tm-neg/60 px-3 py-1 font-tm-mono text-xs font-semibold text-tm-neg hover:bg-tm-neg/20"
          >
            {t(locale, "backtest.verdict.reRun")}
          </button>
        </div>
        {showDetail ? (
          <details className="font-tm-mono text-xs text-tm-muted">
            <summary className="cursor-pointer select-none hover:text-tm-fg-2">
              {t(locale, "backtest.verdict.errorDetails")}
            </summary>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded border border-tm-rule bg-tm-bg px-2 py-1.5 text-[11px] leading-snug">
              {parsed.detail}
            </pre>
          </details>
        ) : null}
      </section>
    );
  }

  // 4 + 5. ok — render metrics. Deltas only shown when recentRunsCount >= 2.
  // Defensive: if ok but somehow no currentRun, fall through to idle copy.
  if (!currentRun) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm text-tm-muted">
        {t(locale, "backtest.verdict.idle")}
      </section>
    );
  }

  const showDeltas = recentRunsCount >= 2;
  const m = currentRun.metrics;
  const isPinned = currentRun.id === baselineRunId;

  const deltaDetail = (delta: MetricDelta | null, formatter: (value: number) => string) =>
    showDeltas && delta ? `${formatter(delta.diff)} ${t(locale, "backtest.runs.baselineMark")}` : undefined;

  return (
    <DecisionStrip
      headline={<BacktestVerdictHeadline raw={currentRun.raw} />}
      description={baselineRunId
        ? (locale === "zh" ? "当前运行与固定基线同屏比较，差值无需心算。" : "Current run is compared with the pinned baseline; deltas require no mental math.")
        : (locale === "zh" ? "固定一项可信运行后，这里将持续显示基线差值。" : "Pin a credible run to keep baseline deltas visible here.")}
      metrics={[
        { label: t(locale, "backtest.metric.sharpe"), value: fmtSharpe(m.sharpe), detail: deltaDetail(deltas.sharpe, fmtDeltaSharpe), tone: decisionTone(m.sharpe === null ? null : classifySharpe(m.sharpe, thresholds)) },
        { label: t(locale, "backtest.metric.maxDd"), value: fmtMaxDD(m.maxDD), detail: deltaDetail(deltas.maxDD, fmtDeltaPercentage1dp), tone: decisionTone(m.maxDD === null ? null : classifyMaxDD(m.maxDD, thresholds)) },
        { label: t(locale, "backtest.metric.ic"), value: fmtIC(m.ic), detail: deltaDetail(deltas.ic, fmtDeltaIC), tone: decisionTone(m.ic === null ? null : classifyIC(m.ic, thresholds)) },
        { label: t(locale, "backtest.metric.turnover"), value: fmtTurnover(m.turnover), detail: deltaDetail(deltas.turnover, fmtDeltaPercentage0dp), tone: decisionTone(m.turnover === null ? null : classifyTurnover(m.turnover, thresholds)) },
        { label: t(locale, "backtest.metric.annReturn"), value: fmtAnnReturn(m.annReturn), detail: deltaDetail(deltas.annReturn, fmtDeltaPercentage1dp), tone: decisionTone(m.annReturn === null ? null : classifyAnnReturn(m.annReturn, thresholds)) },
      ]}
      action={(
        <div className="grid gap-2">
        <button
          type="button"
          onClick={onSaveToZoo}
          aria-label={t(locale, "backtest.action.saveToZoo")}
          className="inline-flex items-center justify-center gap-1 border border-tm-rule bg-tm-bg px-3 py-1.5 font-tm-mono text-[10px] font-semibold text-tm-fg hover:border-tm-accent"
        >
          <Bookmark className="h-3.5 w-3.5" strokeWidth={1.75} />
          {t(locale, "backtest.action.saveToZoo")}
        </button>
        <button
          type="button"
          onClick={onTogglePin}
          aria-label={
            isPinned
              ? t(locale, "backtest.action.unpin")
              : t(locale, "backtest.action.pinAsBaseline")
          }
          aria-pressed={isPinned}
          className="inline-flex items-center justify-center gap-1 border border-tm-rule bg-tm-bg px-3 py-1.5 font-tm-mono text-[10px] font-semibold text-tm-fg hover:border-tm-accent"
        >
          <Star
            className="h-3.5 w-3.5"
            strokeWidth={1.75}
            fill={isPinned ? "currentColor" : "none"}
          />
          {isPinned
            ? t(locale, "backtest.action.unpin")
            : t(locale, "backtest.action.pinAsBaseline")}
        </button>
        </div>
      )}
    />
  );
}
