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

// Shared control geometry so every field box (select / number / checkbox /
// button) lands on the SAME height and fills its grid track. `h-9` (36px) is
// the single source of truth for control height across both rows — change it
// here and the entire form stays aligned. Inputs keep mono for numerics; the
// box border / bg match the terminal palette.
const CONTROL_BOX =
  "flex h-9 w-full items-center rounded border border-tm-rule bg-tm-bg-3 px-2 font-tm-mono text-xs text-tm-fg transition-colors focus-within:border-tm-accent focus:border-tm-accent focus:outline-none";

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

        {/* Row 2 — quick params + RUN button (always visible). A single flex
            row: the three labelled fields grow equally (flex-1) so they fill
            the width with no dead gap, and the toggle + RUN action cluster sits
            flush at the trailing edge, bottom-aligned to the control baseline.
            Even, gap-free tiles instead of fixed-track bricks with a void. */}
        <div className="flex flex-wrap items-end gap-3">
          <FieldShell
            label={t(locale, "backtest.form.direction")}
            className="min-w-[160px] flex-1"
          >
            <select
              value={params.direction}
              onChange={(e) =>
                updateField("direction", e.target.value as DirectionMode)
              }
              className={CONTROL_BOX}
            >
              {DIRECTION_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d.replace("_", " ")}
                </option>
              ))}
            </select>
          </FieldShell>

          <FieldShell
            label={t(locale, "backtest.form.topPct")}
            className="min-w-[120px] flex-1"
          >
            <NumberWithSuffix
              value={params.topPct}
              min={1}
              max={50}
              step={1}
              suffix="%"
              onChange={(n) => updateField("topPct", n)}
            />
          </FieldShell>

          <FieldShell
            label={t(locale, "backtest.form.universe")}
            className="min-w-[150px] flex-1"
          >
            <select
              value={params.universe === "custom" ? "SP500" : params.universe}
              onChange={(e) =>
                updateField("universe", e.target.value as FactorUniverse)
              }
              className={CONTROL_BOX}
            >
              {UNIVERSE_OPTIONS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </FieldShell>

          {/* Toggle + RUN — trailing action cluster, bottom-aligned to the
              input baseline of the fields to its left. */}
          <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={() => setAdvancedOpen((o) => !o)}
              aria-expanded={advancedOpen}
              className="inline-flex h-9 shrink-0 items-center gap-1 rounded border border-tm-rule px-2.5 font-tm-mono text-[11px] text-tm-fg-2 transition-colors hover:border-tm-accent hover:text-tm-fg"
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

            <button
              type="button"
              onClick={onRun}
              disabled={runDisabled}
              className="inline-flex h-9 items-center gap-2 rounded bg-tm-accent px-4 font-tm-mono text-xs font-semibold uppercase tracking-wider text-tm-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
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
          <div className="flex flex-wrap items-start gap-3 border-t border-tm-rule pt-3">
            <FieldShell
              label={t(locale, "backtest.form.bottomPct")}
              className="min-w-[120px] flex-1"
            >
              <NumberWithSuffix
                value={params.bottomPct}
                min={1}
                max={50}
                step={1}
                suffix="%"
                onChange={(n) => updateField("bottomPct", n)}
              />
            </FieldShell>

            <FieldShell
              label={t(locale, "backtest.form.lookback")}
              className="min-w-[120px] flex-1"
            >
              <NumberWithSuffix
                value={params.lookback}
                min={10}
                max={2000}
                step={1}
                suffix="d"
                onChange={(n) => updateField("lookback", n)}
              />
            </FieldShell>

            <FieldShell
              label={t(locale, "backtest.form.benchmark")}
              className="min-w-[120px] flex-1"
            >
              <select
                value={params.benchmark}
                onChange={(e) =>
                  updateField("benchmark", e.target.value as "SPY" | "RSP")
                }
                className={CONTROL_BOX}
              >
                {BENCHMARK_OPTIONS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </FieldShell>

            {/* Neutralize — boxed checkbox cell with the same h-9 control
                height + border/bg as its row-mates, so the toggle reads as a
                field control instead of floating between the inputs. */}
            <FieldShell
              label={t(locale, "backtest.form.neutralize")}
              className="min-w-[140px] flex-1"
            >
              <div className={`${CONTROL_BOX} cursor-pointer gap-2`}>
                <input
                  type="checkbox"
                  checked={params.neutralize}
                  onChange={(e) => updateField("neutralize", e.target.checked)}
                  className="shrink-0 cursor-pointer accent-[var(--tm-accent)]"
                />
                <span className="truncate">
                  {params.neutralize
                    ? t(locale, "backtest.form.neutralize.sector")
                    : t(locale, "backtest.form.neutralize.none")}
                </span>
              </div>
            </FieldShell>

            <FieldShell
              label={t(locale, "backtest.form.costBps")}
              className="min-w-[120px] flex-1"
            >
              <NumberWithSuffix
                value={params.transactionCostBps}
                min={0}
                max={50}
                step={1}
                suffix="bps"
                onChange={(n) => updateField("transactionCostBps", n)}
              />
            </FieldShell>

            <FieldShell
              label={t(locale, "backtest.form.modeLabel")}
              className="min-w-[140px] flex-1"
            >
              <select
                value={params.mode}
                onChange={(e) =>
                  updateField("mode", e.target.value as BacktestMode)
                }
                className={CONTROL_BOX}
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
  className,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
  readonly className?: string;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 ${className ?? ""}`}>
      <span className="font-tm-sans text-[11px] font-semibold uppercase leading-none tracking-[0.06em] text-tm-muted">
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
    <div className={`${CONTROL_BOX} gap-1`}>
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
        className="min-w-0 flex-1 bg-transparent font-tm-mono text-xs tabular-nums text-tm-fg outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <span className="shrink-0 font-tm-mono text-[11px] text-tm-muted">{suffix}</span>
    </div>
  );
}
