"use client";

/**
 * BacktestFormSticky — sticky-top form for the /backtest redesign.
 *
 * Layout (per /backtest redesign spec §3 Task 3):
 *  Row 1: full-width expression <textarea>, font-tm-mono, monospaced.
 *  Row 2 (always visible): direction · top% · universe · "+ Advanced"
 *         toggle · RUN BACKTEST primary action.
 *  Row 3 (collapsible, hidden by default): bottom% · lookback · benchmark
 *         · neutralize · transaction_cost_bps · mode.
 *
 * Container is `sticky top-0 z-30` so it stays anchored as the user scrolls
 * the verdict / evidence panes below.
 *
 * `operatorsUsed` derivation: the hook (`useBacktestSession.buildRequest`)
 * reads `params.operatorsUsed` directly when constructing the FactorSpec.
 * Instead of surfacing operators as a user-editable control, we keep them
 * in lockstep with `params.expression` by recomputing via `extractOps()`
 * inside the textarea onChange. This matches `TmBacktestForm.submit()` (which
 * derives ops at submit time) and avoids stale state when the user runs
 * without focus-blur. The backend re-validates against its AST whitelist
 * anyway, so a naive regex extraction is sufficient.
 */

import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Play } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  extractOperands,
  extractOps,
  isAllowedOp,
  isAllowedOperand,
  suggestOp,
  suggestOperand,
} from "@/lib/factor-spec";
import type { FactorUniverse } from "@/lib/types";
import type { BacktestMode, BacktestParams, DirectionMode } from "./types";

interface BacktestFormStickyProps {
  readonly params: BacktestParams;
  readonly setParams: React.Dispatch<React.SetStateAction<BacktestParams>>;
  readonly isRunning: boolean;
  readonly onRun: () => void;
}

// `custom` is API-only — do not expose to the user. Spec §3 explicitly
// scopes the UI to the three real universes.
const UNIVERSE_OPTIONS: ReadonlyArray<Exclude<FactorUniverse, "custom">> = [
  "SP500",
  "CSI300",
  "CSI500",
];

const DIRECTION_OPTIONS: ReadonlyArray<DirectionMode> = [
  "long_short",
  "long_only",
  "short_only",
];

const MODE_OPTIONS: ReadonlyArray<BacktestMode> = ["static", "walk_forward"];

const BENCHMARK_OPTIONS: ReadonlyArray<"SPY" | "RSP"> = ["SPY", "RSP"];

export function BacktestFormSticky({
  params,
  setParams,
  isRunning,
  onRun,
}: BacktestFormStickyProps) {
  const { locale } = useLocale();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const exprEmpty = params.expression.trim().length === 0;
  // Catch typos like `ts_means` BEFORE the backend bounces a verbose 422.
  // operatorsUsed is recomputed in updateExpression via extractOps, so this
  // stays in lockstep with the textarea. Each entry is paired with its
  // nearest-neighbor suggestion (Levenshtein ≤2) when one exists.
  const unknownOps = useMemo(
    () =>
      params.operatorsUsed
        .filter((op) => !isAllowedOp(op))
        .map((op) => ({ op, suggestion: suggestOp(op) })),
    [params.operatorsUsed],
  );
  // Parallel guard for leaf operands (data columns like `returns`, `close`).
  // The backend returns HTTP 400 with `unknown operand 'X'` for these, which
  // the existing 422 parser previously couldn't recognize; pre-filter here
  // to disable the RUN button before the round-trip. We exclude any name
  // that is ALSO a known operator — the backend's AST walk permits bare
  // operator names as ast.Name matches (factor_ast.py:157), so flagging
  // them as "unknown operand" would be a false positive.
  const unknownOperands = useMemo(
    () =>
      extractOperands(params.expression)
        .filter((o) => !isAllowedOperand(o) && !isAllowedOp(o))
        .map((o) => ({ operand: o, suggestion: suggestOperand(o) })),
    [params.expression],
  );
  const hasUnknownOps = unknownOps.length > 0;
  const hasUnknownOperands = unknownOperands.length > 0;
  const hasValidationIssues = hasUnknownOps || hasUnknownOperands;
  const runDisabled = exprEmpty || isRunning || hasValidationIssues;

  function updateExpression(next: string) {
    // Keep operators_used coherent with expression text. The hook reads
    // params.operatorsUsed directly when building the request, so any
    // drift here surfaces as an AST-whitelist mismatch from the backend.
    setParams((p) => ({
      ...p,
      expression: next,
      operatorsUsed: extractOps(next),
    }));
  }

  function updateField<K extends keyof BacktestParams>(
    key: K,
    value: BacktestParams[K],
  ) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  return (
    <section
      className="sticky top-0 z-30 border-b border-tm-rule bg-tm-bg-2/95 backdrop-blur supports-[backdrop-filter]:bg-tm-bg-2/80"
      aria-label={t(locale, "backtest.form.title")}
    >
      <div className="flex flex-col gap-3 px-4 py-3">
        {/* Row 1 — expression textarea */}
        <textarea
          value={params.expression}
          onChange={(e) => updateExpression(e.target.value)}
          placeholder={t(locale, "backtest.form.exprPlaceholder")}
          spellCheck={false}
          rows={1}
          aria-label={t(locale, "backtest.form.title")}
          className="min-h-[36px] w-full resize-y rounded border border-tm-rule bg-tm-bg-3 px-3 py-2 font-tm-mono text-[12px] leading-relaxed text-tm-fg outline-none transition-[min-height,border-color] placeholder:text-tm-muted focus:min-h-[96px] focus:border-tm-accent"
          aria-invalid={hasValidationIssues || undefined}
          aria-describedby={
            hasValidationIssues ? "backtest-unknown-ops" : undefined
          }
        />

        {/* Inline validation — unknown ops/operands before backend 4xx.
            Single panel listing both categories keeps visual noise low; each
            row carries its own "Unknown operator" vs "Unknown data field"
            label so users can disambiguate at a glance. */}
        {hasValidationIssues && (
          <div
            id="backtest-unknown-ops"
            role="alert"
            className="flex flex-col gap-1 rounded border border-tm-warn/40 bg-tm-warn/5 px-3 py-2 font-tm-mono text-[11px] text-tm-warn"
          >
            {unknownOps.map(({ op, suggestion }) => (
              <div key={`op-${op}`}>
                <span>{t(locale, "backtest.form.unknownOp")}: </span>
                <code className="rounded bg-tm-bg-3 px-1 py-0.5 text-tm-fg">{op}</code>
                {suggestion !== null && (
                  <>
                    <span> — {t(locale, "backtest.form.didYouMean")} </span>
                    <code className="rounded bg-tm-bg-3 px-1 py-0.5 text-tm-pos">
                      {suggestion}
                    </code>
                    <span>?</span>
                  </>
                )}
              </div>
            ))}
            {unknownOperands.map(({ operand, suggestion }) => (
              <div key={`opd-${operand}`}>
                <span>{t(locale, "backtest.form.unknownOperand")}: </span>
                <code className="rounded bg-tm-bg-3 px-1 py-0.5 text-tm-fg">
                  {operand}
                </code>
                {suggestion !== null && (
                  <>
                    <span> — {t(locale, "backtest.form.didYouMean")} </span>
                    <code className="rounded bg-tm-bg-3 px-1 py-0.5 text-tm-pos">
                      {suggestion}
                    </code>
                    <span>?</span>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Row 2 — quick params + RUN button (always visible) */}
        <div className="flex flex-wrap items-end gap-3">
          <FieldShell label={t(locale, "backtest.form.direction")}>
            <select
              value={params.direction}
              onChange={(e) =>
                updateField("direction", e.target.value as DirectionMode)
              }
              className="rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-fg focus:border-tm-accent focus:outline-none"
            >
              {DIRECTION_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d.replace("_", " ")}
                </option>
              ))}
            </select>
          </FieldShell>

          <FieldShell label={t(locale, "backtest.form.topPct")}>
            <NumberWithSuffix
              value={params.topPct}
              min={1}
              max={50}
              step={1}
              suffix="%"
              onChange={(n) => updateField("topPct", n)}
            />
          </FieldShell>

          <FieldShell label={t(locale, "backtest.form.universe")}>
            <select
              value={params.universe === "custom" ? "SP500" : params.universe}
              onChange={(e) =>
                updateField("universe", e.target.value as FactorUniverse)
              }
              className="rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-fg focus:border-tm-accent focus:outline-none"
            >
              {UNIVERSE_OPTIONS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </FieldShell>

          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            aria-expanded={advancedOpen}
            className="inline-flex items-center gap-1 rounded border border-tm-rule px-2.5 py-1 font-tm-mono text-[11px] text-tm-fg-2 transition-colors hover:border-tm-accent hover:text-tm-fg"
          >
            {advancedOpen ? (
              <ChevronUp className="h-3 w-3" strokeWidth={1.75} />
            ) : (
              <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
            )}
            <span>
              {advancedOpen
                ? t(locale, "backtest.action.advancedHide")
                : t(locale, "backtest.action.advancedShow")}
            </span>
          </button>

          <div className="ml-auto">
            <button
              type="button"
              onClick={onRun}
              disabled={runDisabled}
              className="inline-flex items-center gap-2 rounded bg-tm-accent px-4 py-2 font-tm-mono text-[12px] font-semibold uppercase tracking-wider text-tm-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isRunning ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
                  <span>{t(locale, "backtest.verdict.running")}</span>
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5" strokeWidth={2} />
                  <span>{t(locale, "backtest.action.runBacktest")}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Row 3 — Advanced 6-field collapsible */}
        <div
          className={`grid overflow-hidden transition-[max-height,opacity] duration-200 ${
            advancedOpen ? "max-h-60 opacity-100" : "max-h-0 opacity-0"
          }`}
          aria-hidden={!advancedOpen}
        >
          <div className="grid grid-cols-2 gap-3 border-t border-tm-rule pt-3 md:grid-cols-3 lg:grid-cols-6">
            <FieldShell label={t(locale, "backtest.form.bottomPct")}>
              <NumberWithSuffix
                value={params.bottomPct}
                min={1}
                max={50}
                step={1}
                suffix="%"
                onChange={(n) => updateField("bottomPct", n)}
              />
            </FieldShell>

            <FieldShell label={t(locale, "backtest.form.lookback")}>
              <NumberWithSuffix
                value={params.lookback}
                min={10}
                max={2000}
                step={1}
                suffix="d"
                onChange={(n) => updateField("lookback", n)}
              />
            </FieldShell>

            <FieldShell label={t(locale, "backtest.form.benchmark")}>
              <select
                value={params.benchmark}
                onChange={(e) =>
                  updateField("benchmark", e.target.value as "SPY" | "RSP")
                }
                className="rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-fg focus:border-tm-accent focus:outline-none"
              >
                {BENCHMARK_OPTIONS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </FieldShell>

            <FieldShell label={t(locale, "backtest.form.neutralize")}>
              <label className="inline-flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg">
                <input
                  type="checkbox"
                  checked={params.neutralize}
                  onChange={(e) => updateField("neutralize", e.target.checked)}
                  className="cursor-pointer accent-[var(--tm-accent)]"
                />
                <span>
                  {params.neutralize
                    ? t(locale, "backtest.form.neutralize.sector")
                    : t(locale, "backtest.form.neutralize.none")}
                </span>
              </label>
            </FieldShell>

            <FieldShell label={t(locale, "backtest.form.costBps")}>
              <NumberWithSuffix
                value={params.transactionCostBps}
                min={0}
                max={50}
                step={1}
                suffix="bps"
                onChange={(n) => updateField("transactionCostBps", n)}
              />
            </FieldShell>

            <FieldShell label={t(locale, "backtest.form.modeLabel")}>
              <select
                value={params.mode}
                onChange={(e) =>
                  updateField("mode", e.target.value as BacktestMode)
                }
                className="rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 font-tm-mono text-[11px] text-tm-fg focus:border-tm-accent focus:outline-none"
              >
                {MODE_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {t(
                      locale,
                      m === "static"
                        ? "backtest.form.modeStatic"
                        : "backtest.form.modeWalkForward",
                    )}
                  </option>
                ))}
              </select>
            </FieldShell>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Primitives ──────────────────────────────────────────────────── */

function FieldShell({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </span>
      {children}
    </label>
  );
}

function NumberWithSuffix({
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step: number;
  readonly suffix: string;
  readonly onChange: (n: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg-3 px-2 py-1 focus-within:border-tm-accent">
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
        className="w-14 bg-transparent font-mono text-[11px] tabular-nums text-tm-fg outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <span className="font-tm-mono text-[10px] text-tm-muted">{suffix}</span>
    </div>
  );
}
