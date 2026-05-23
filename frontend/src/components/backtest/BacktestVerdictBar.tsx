"use client";

import {
  AlertCircle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Bookmark,
  Loader2,
  Star,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { parseBacktestError } from "./errorParse";
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

/* ---------- Glyph + delta arrow renderers ---------- */

const GLYPH: Record<TrafficLight, JSX.Element> = {
  ok: <span className="ml-1 text-tm-pos">&#10003;</span>,
  warn: <span className="ml-1 text-tm-warn">&#9888;</span>,
  bad: <span className="ml-1 text-tm-neg">&#10007;</span>,
};

/**
 * Render a delta arrow. Direction (↑↓→) reflects raw signed comparison;
 * color is decoupled and driven by `betterThanBaseline` so e.g. turnover
 * going UP shows ↑ in red (worse), Sharpe going DOWN shows ↓ in red.
 */
function DeltaArrow({
  delta,
  diffLabel,
}: {
  readonly delta: MetricDelta;
  readonly diffLabel: string;
}) {
  const colorClass =
    delta.arrow === "flat"
      ? "text-tm-muted"
      : delta.betterThanBaseline
      ? "text-tm-pos"
      : "text-tm-neg";
  const Icon =
    delta.arrow === "up"
      ? ArrowUp
      : delta.arrow === "down"
      ? ArrowDown
      : ArrowRight;
  return (
    <span
      className={`ml-1 inline-flex items-center gap-0.5 text-xs ${colorClass}`}
    >
      <Icon className="h-3 w-3" strokeWidth={1.75} />
      <span className="font-mono">{diffLabel}</span>
    </span>
  );
}

interface MetricCellProps {
  readonly label: string;
  readonly valueText: string;
  readonly glyph: TrafficLight | null;
  readonly thresholdTitle: string;
  readonly delta: MetricDelta | null;
  readonly diffLabel: string | null;
}

function MetricCell({
  label,
  valueText,
  glyph,
  thresholdTitle,
  delta,
  diffLabel,
}: MetricCellProps) {
  return (
    <span
      title={thresholdTitle}
      className="cursor-help text-tm-fg inline-flex items-center"
    >
      <span className="text-tm-muted">{label}=</span>
      <span className="font-mono ml-0.5">{valueText}</span>
      {glyph && GLYPH[glyph]}
      {delta && diffLabel && <DeltaArrow delta={delta} diffLabel={diffLabel} />}
    </span>
  );
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
    const parsed = parseBacktestError(runState.message);
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

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <MetricCell
          label={t(locale, "backtest.metric.sharpe")}
          valueText={fmtSharpe(m.sharpe)}
          glyph={m.sharpe === null ? null : classifySharpe(m.sharpe, thresholds)}
          thresholdTitle={t(locale, "backtest.threshold.sharpe")}
          delta={showDeltas ? deltas.sharpe : null}
          diffLabel={
            showDeltas && deltas.sharpe ? fmtDeltaSharpe(deltas.sharpe.diff) : null
          }
        />
        <MetricCell
          label={t(locale, "backtest.metric.maxDd")}
          valueText={fmtMaxDD(m.maxDD)}
          glyph={m.maxDD === null ? null : classifyMaxDD(m.maxDD, thresholds)}
          thresholdTitle={t(locale, "backtest.threshold.maxDd")}
          delta={showDeltas ? deltas.maxDD : null}
          diffLabel={
            showDeltas && deltas.maxDD
              ? fmtDeltaPercentage1dp(deltas.maxDD.diff)
              : null
          }
        />
        <MetricCell
          label={t(locale, "backtest.metric.ic")}
          valueText={fmtIC(m.ic)}
          glyph={m.ic === null ? null : classifyIC(m.ic, thresholds)}
          thresholdTitle={t(locale, "backtest.threshold.ic")}
          delta={showDeltas ? deltas.ic : null}
          diffLabel={showDeltas && deltas.ic ? fmtDeltaIC(deltas.ic.diff) : null}
        />
        <MetricCell
          label={t(locale, "backtest.metric.turnover")}
          valueText={fmtTurnover(m.turnover)}
          glyph={
            m.turnover === null ? null : classifyTurnover(m.turnover, thresholds)
          }
          thresholdTitle={t(locale, "backtest.threshold.turnover")}
          delta={showDeltas ? deltas.turnover : null}
          diffLabel={
            showDeltas && deltas.turnover
              ? fmtDeltaPercentage0dp(deltas.turnover.diff)
              : null
          }
        />
        <MetricCell
          label={t(locale, "backtest.metric.annReturn")}
          valueText={fmtAnnReturn(m.annReturn)}
          glyph={
            m.annReturn === null
              ? null
              : classifyAnnReturn(m.annReturn, thresholds)
          }
          thresholdTitle={t(locale, "backtest.threshold.annReturn")}
          delta={showDeltas ? deltas.annReturn : null}
          diffLabel={
            showDeltas && deltas.annReturn
              ? fmtDeltaPercentage1dp(deltas.annReturn.diff)
              : null
          }
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onSaveToZoo}
          aria-label={t(locale, "backtest.action.saveToZoo")}
          className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg px-3 py-1.5 font-tm-mono text-xs font-semibold text-tm-fg hover:bg-tm-bg-2"
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
          className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg px-3 py-1.5 font-tm-mono text-xs font-semibold text-tm-fg hover:bg-tm-bg-2"
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
    </section>
  );
}
