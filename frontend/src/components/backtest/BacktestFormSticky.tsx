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

import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Library,
  Play,
  Save,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { HoverTip } from "@/components/ui/HoverTip";
import { TmButton } from "@/components/tm/TmButton";
import {
  TmCheckbox,
  TmFieldShell,
  TmNumberInput,
  TmSelect,
  TmTextarea,
} from "@/components/tm/TmField";
import {
  extractOperands,
  extractOps,
  isAllowedOp,
  isAllowedOperand,
  suggestOp,
  suggestOperand,
} from "@/lib/factor-spec";
import {
  listZoo,
  readDirection,
  seedZooIfFirstRun,
  type ZooEntry,
} from "@/lib/factor-zoo";
import type { FactorUniverse } from "@/lib/types";
import type { BacktestMode, BacktestParams, DirectionMode } from "./types";
import { DEFAULT_PARAMS } from "./useBacktestSession";

interface BacktestFormStickyProps {
  readonly params: BacktestParams;
  readonly setParams: React.Dispatch<React.SetStateAction<BacktestParams>>;
  readonly isRunning: boolean;
  readonly onRun: () => void;
}

// The web backtest engine is hard-fixed to the pre-cached SP500 panel
// (factor_backtest.py ignores spec.universe; there is no A-share data), so
// CSI300/CSI500 were dead options that silently returned SP500 results.
// SP500 is the only real choice. `custom` is API-only — not exposed here.
const UNIVERSE_OPTIONS: ReadonlyArray<Exclude<FactorUniverse, "custom">> = [
  "SP500",
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

  // Saved factors for the "Load from Zoo" picker — so the user can pull a
  // saved factor straight into the expression instead of retyping it.
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  useEffect(() => {
    seedZooIfFirstRun();
    setZoo(listZoo());
  }, []);

  // Apply a saved factor's expression + its proven config to the form (mirrors
  // the /alpha · /factors prefill mapping; topPct/bottomPct are stored as
  // fractions, the form carries 0–100 percentages). Does NOT auto-run.
  function loadFromZoo(entry: ZooEntry) {
    setParams((p) => ({
      ...p,
      expression: entry.expression,
      operatorsUsed: extractOps(entry.expression),
      direction: readDirection(entry),
      neutralize:
        entry.neutralize != null ? entry.neutralize === "sector" : p.neutralize,
      benchmark: entry.benchmarkTicker ?? p.benchmark,
      mode: entry.mode ?? p.mode,
      topPct: entry.topPct != null ? entry.topPct * 100 : p.topPct,
      bottomPct: entry.bottomPct != null ? entry.bottomPct * 100 : p.bottomPct,
      transactionCostBps: entry.transactionCostBps ?? p.transactionCostBps,
    }));
  }

  // Reset to defaults; the page's persist effect then overwrites the saved
  // localStorage form with defaults, so "memory" is cleared too (Forgiveness).
  function resetForm() {
    setParams(DEFAULT_PARAMS);
  }

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
      className="sticky top-0 z-30 border-b border-tm-rule bg-tm-bg-2"
      aria-label={t(locale, "backtest.form.title")}
    >
      <div className="flex flex-col gap-3 px-6 py-3">
        {/* Row 0 — load a saved factor + surface that the form auto-saves */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* Load from Zoo: pull a saved factor straight into the expression */}
          <TmSelect
            label={(
              <span className="flex items-center gap-2">
                <Library className="h-3.5 w-3.5" strokeWidth={1.75} />
                {t(locale, "backtest.loadZoo.label")}
              </span>
            )}
            className="min-w-0 flex-row items-center gap-2"
            fieldSize="md"
            value=""
            onChange={(value) => {
              const entry = zoo.find((z) => z.id === value);
              if (entry) loadFromZoo(entry);
            }}
            disabled={zoo.length === 0}
            selectClassName="w-auto min-w-[10rem] text-tm-accent"
            options={[
              {
                value: "",
                label:
                  zoo.length === 0
                    ? t(locale, "backtest.loadZoo.empty")
                    : t(locale, "backtest.loadZoo.placeholder"),
              },
              ...zoo.map((entry) => ({ value: entry.id, label: entry.name })),
            ]}
          />

          {/* Autosave indicator (discoverability) + reset (Forgiveness) */}
          <div className="flex items-center gap-2 font-tm-mono text-xs text-tm-muted">
            <HoverTip content={t(locale, "backtest.memory.hint")} width={260}>
              <span className="inline-flex cursor-help items-center gap-1 border-b border-dotted border-tm-muted/50 hover:border-tm-fg">
                <Save className="h-3 w-3" strokeWidth={1.75} />
                {t(locale, "backtest.memory.label")}
              </span>
            </HoverTip>
            <TmButton variant="ghost" size="md" onClick={resetForm}>
              {t(locale, "backtest.memory.reset")}
            </TmButton>
          </div>
        </div>

        <div className="grid items-end gap-3 xl:grid-cols-[minmax(320px,1.35fr)_minmax(720px,2.65fr)]">
          <div>
            <TmTextarea
              label={t(locale, "backtest.form.title")}
              value={params.expression}
              onChange={updateExpression}
              placeholder={t(locale, "backtest.form.exprPlaceholder")}
              spellCheck={false}
              rows={1}
              id="backtest-expression"
              aria-invalid={hasValidationIssues || undefined}
              aria-describedby={
                hasValidationIssues ? "backtest-unknown-ops" : undefined
              }
              className="min-w-0"
              textareaClassName="h-8 min-h-8 w-full resize-y bg-tm-bg px-3 py-2 text-[12px] leading-relaxed text-tm-accent transition-[min-height,border-color] focus:min-h-[84px]"
            />

        {/* Inline validation — unknown ops/operands before backend 4xx.
            Single panel listing both categories keeps visual noise low; each
            row carries its own "Unknown operator" vs "Unknown data field"
            label so users can disambiguate at a glance. */}
            {hasValidationIssues && (
          <div
            id="backtest-unknown-ops"
            role="alert"
            className="mt-2 flex flex-col gap-1 border border-tm-warn/40 bg-tm-warn/5 px-3 py-2 font-tm-mono text-xs text-tm-warn"
          >
            {unknownOps.map(({ op, suggestion }) => (
              <div key={`op-${op}`}>
                <span>{t(locale, "backtest.form.unknownOp")}: </span>
                <code className="rounded-[2px] bg-tm-bg-3 px-1 py-0.5 text-tm-fg">{op}</code>
                {suggestion !== null && (
                  <>
                    <span> — {t(locale, "backtest.form.didYouMean")} </span>
                    <code className="rounded-[2px] bg-tm-bg-3 px-1 py-0.5 text-tm-pos">
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
                <code className="rounded-[2px] bg-tm-bg-3 px-1 py-0.5 text-tm-fg">
                  {operand}
                </code>
                {suggestion !== null && (
                  <>
                    <span> — {t(locale, "backtest.form.didYouMean")} </span>
                    <code className="rounded-[2px] bg-tm-bg-3 px-1 py-0.5 text-tm-pos">
                      {suggestion}
                    </code>
                    <span>?</span>
                  </>
                )}
              </div>
            ))}
          </div>
            )}
          </div>

        {/* Row 2 — quick params + RUN button (always visible). A single flex
            row: the three labelled fields grow equally (flex-1) so they fill
            the width with no dead gap, and the toggle + RUN action cluster sits
            flush at the trailing edge, bottom-aligned to the control baseline.
            Even, gap-free tiles instead of fixed-track bricks with a void. */}
          <div className="flex flex-wrap items-end gap-3">
          <TmSelect
            label={t(locale, "backtest.form.direction")}
            className="min-w-[160px] flex-1"
            fieldSize="md"
            value={params.direction}
            onChange={(value) =>
              updateField("direction", value as DirectionMode)
            }
            options={DIRECTION_OPTIONS.map((option) => ({
              value: option,
              label: option.replace("_", " "),
            }))}
          />

          <TmNumberInput
            label={t(locale, "backtest.form.topPct")}
            className="min-w-[120px] flex-1"
            fieldSize="md"
            value={params.topPct}
            min={1}
            max={50}
            step={1}
            suffix="%"
            onChange={(value) => updateField("topPct", value)}
          />

          <TmSelect
            label={t(locale, "backtest.form.universe")}
            className="min-w-[150px] flex-1"
            fieldSize="md"
            value={params.universe === "custom" ? "SP500" : params.universe}
            onChange={(value) =>
              updateField("universe", value as FactorUniverse)
            }
            options={UNIVERSE_OPTIONS.map((option) => ({
              value: option,
              label: option,
            }))}
          />

          {/* Toggle + RUN — trailing action cluster, bottom-aligned to the
              input baseline of the fields to its left. */}
          <div className="flex items-end gap-2">
            <TmButton
              variant="secondary"
              size="md"
              onClick={() => setAdvancedOpen((o) => !o)}
              aria-expanded={advancedOpen}
              className="shrink-0"
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
            </TmButton>

            <TmButton
              variant="primary"
              size="md"
              onClick={onRun}
              disabled={runDisabled}
              loading={isRunning}
              loadingLabel={t(locale, "backtest.verdict.running")}
              className="px-5 uppercase tracking-wider"
            >
              <Play className="h-3.5 w-3.5" strokeWidth={2} />
              <span>{t(locale, "backtest.action.runBacktest")}</span>
            </TmButton>
          </div>
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
            <TmNumberInput
              label={t(locale, "backtest.form.bottomPct")}
              className="min-w-[120px] flex-1"
              fieldSize="md"
              value={params.bottomPct}
              min={1}
              max={50}
              step={1}
              suffix="%"
              onChange={(value) => updateField("bottomPct", value)}
            />

            <TmNumberInput
              label={t(locale, "backtest.form.lookback")}
              className="min-w-[120px] flex-1"
              fieldSize="md"
              value={params.lookback}
              min={10}
              max={2000}
              step={1}
              suffix="d"
              onChange={(value) => updateField("lookback", value)}
            />

            <TmSelect
              label={t(locale, "backtest.form.benchmark")}
              className="min-w-[120px] flex-1"
              fieldSize="md"
              value={params.benchmark}
              onChange={(value) =>
                updateField("benchmark", value as "SPY" | "RSP")
              }
              options={BENCHMARK_OPTIONS.map((option) => ({
                value: option,
                label: option,
              }))}
            />

            <TmFieldShell
              label={t(locale, "backtest.form.neutralize")}
              className="min-w-[140px] flex-1"
              htmlFor="backtest-neutralize"
            >
              <TmCheckbox
                id="backtest-neutralize"
                checked={params.neutralize}
                onChange={(checked) => updateField("neutralize", checked)}
                label={
                  params.neutralize
                    ? t(locale, "backtest.form.neutralize.sector")
                    : t(locale, "backtest.form.neutralize.none")
                }
              />
            </TmFieldShell>

            <TmNumberInput
              label={t(locale, "backtest.form.costBps")}
              className="min-w-[120px] flex-1"
              fieldSize="md"
              value={params.transactionCostBps}
              min={0}
              max={50}
              step={1}
              suffix="bps"
              onChange={(value) => updateField("transactionCostBps", value)}
            />

            <TmSelect
              label={t(locale, "backtest.form.modeLabel")}
              className="min-w-[140px] flex-1"
              fieldSize="md"
              value={params.mode}
              onChange={(value) =>
                updateField("mode", value as BacktestMode)
              }
              options={MODE_OPTIONS.map((option) => ({
                value: option,
                label: t(
                  locale,
                  option === "static"
                    ? "backtest.form.modeStatic"
                    : "backtest.form.modeWalkForward",
                ),
              }))}
            />

            <TmFieldShell
              label={t(locale, "backtest.form.includeBreakdown")}
              className="min-w-[220px] flex-[1.4]"
              htmlFor="backtest-include-breakdown"
            >
              <TmCheckbox
                id="backtest-include-breakdown"
                checked={params.includeBreakdown}
                onChange={(checked) => updateField("includeBreakdown", checked)}
                hint={t(locale, "backtest.form.includeBreakdownHint")}
                label={
                  params.includeBreakdown
                    ? (locale === "zh"
                      ? "已开启，约 +200 KB"
                      : "Enabled, about +200 KB")
                    : (locale === "zh"
                      ? "关闭，减少响应体积"
                      : "Off, smaller response")
                }
              />
            </TmFieldShell>
          </div>
        </div>
      </div>
    </section>
  );
}
