"use client";

import { ChevronDown, History, LayoutGrid, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FactorExampleModal } from "@/components/alpha/FactorExampleModal";
import type { FactorExample } from "@/components/alpha/FactorExamples";
import type { FactorUniverse } from "@/lib/types";
import type { AlphaValidationParams } from "@/components/alpha/useAlphaChain";
import { TmButton, TmRowButton } from "@/components/tm/TmButton";
import { TmNumberInput, TmSelect, TmTextarea } from "@/components/tm/TmField";

// ---- Prop types ----

/**
 * Mirrors the real `HypothesisHistoryEntry` from lib/types.ts.
 * Extra fields are typed as optional so the parent can pass the
 * full richer object without a type error.
 */
export interface InputCardHistoryEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly isFavorite?: boolean;
  readonly request: {
    readonly text: string;
    readonly universe?: FactorUniverse;
  };
  readonly result?: {
    readonly spec?: {
      readonly expression?: string;
    };
  };
}

interface Props {
  readonly text: string;
  readonly onTextChange: (s: string) => void;
  readonly universe: FactorUniverse;
  readonly onUniverseChange: (u: FactorUniverse) => void;
  readonly validation: AlphaValidationParams;
  readonly onValidationChange: (params: AlphaValidationParams) => void;
  readonly onSubmit: () => void;
  readonly canRerun: boolean;
  readonly onRerun: () => void;
  readonly disabled: boolean;
  readonly examples: ReadonlyArray<FactorExample>;
  // Selecting a row from the grouped example list (alpha flow loads the
  // example's hypothesis prose into the textarea).
  readonly onExampleSelect: (ex: FactorExample) => void;
  readonly history: ReadonlyArray<InputCardHistoryEntry>;
  readonly onHistorySelect: (entry: InputCardHistoryEntry) => void;
}

// FactorUniverse = "CSI300" | "CSI500" | "SP500" | "custom"
// CSI300/CSI500 dropped: the backend has no A-share data and the LLM only
// emits SP500|custom, so they were non-functional. SP500 + custom remain.
const UNIVERSES: FactorUniverse[] = ["SP500", "custom"];

// ---- Component ----

export function HypothesisInputCard(p: Props) {
  const { locale } = useLocale();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [examplesOpen, setExamplesOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!historyOpen) return;
    function handler(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setHistoryOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [historyOpen]);

  const empty = p.text.trim().length === 0;
  const updateValidation = <K extends keyof AlphaValidationParams>(
    key: K,
    value: AlphaValidationParams[K],
  ) => p.onValidationChange({ ...p.validation, [key]: value });

  return (
    <section className="border-b border-tm-rule bg-tm-bg-2/35 px-6 py-4">
      {/* Header row: section title + History popover trigger */}
      <header className="mb-3 flex items-center justify-between">
        <h2 className="font-tm-mono text-[12px] font-semibold tracking-[0.08em] text-tm-fg">
          <span className="mr-2 text-tm-accent">①</span>
          {t(locale, "alpha.input.title" as Parameters<typeof t>[1])}
          <span className="ml-2 font-normal tracking-normal text-tm-muted">
            {locale === "zh" ? "把研究判断写成一句可被反驳的话" : "Write one claim the data can refute"}
          </span>
        </h2>

        {/* History popover */}
        <div className="relative" ref={popoverRef}>
          <TmButton
            type="button"
            variant="secondary"
            onClick={() => setHistoryOpen((o) => !o)}
            aria-label={t(locale, "alpha.input.historyBtn" as Parameters<typeof t>[1])}
          >
            <History className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>{t(locale, "alpha.input.historyBtn" as Parameters<typeof t>[1])}</span>
            <ChevronDown
              className={`h-3 w-3 transition-transform ${historyOpen ? "rotate-180" : ""}`}
              strokeWidth={1.75}
            />
          </TmButton>

          {historyOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 max-h-[400px] w-[380px] overflow-y-auto rounded-[2px] border border-tm-rule bg-tm-bg-2 shadow-lg">
              {p.history.length === 0 ? (
                <div className="px-3 py-4 font-tm-mono text-xs text-tm-muted">
                  {t(locale, "alpha.historyEmpty" as Parameters<typeof t>[1])}
                </div>
              ) : (
                <ul>
                  {p.history.map((h) => (
                    <li key={h.id} className="border-b border-tm-rule last:border-b-0">
                      <TmRowButton
                        type="button"
                        onClick={() => {
                          p.onHistorySelect(h);
                          setHistoryOpen(false);
                        }}
                        className="block w-full px-3 py-2 text-left transition-colors hover:bg-tm-bg-3"
                      >
                        <div className="line-clamp-2 font-tm-mono text-xs text-tm-fg-2 hover:text-tm-fg">
                          {h.request.text}
                        </div>
                        {h.result?.spec?.expression && (
                          <code className="mt-0.5 block truncate font-mono text-xs text-tm-muted">
                            {h.result.spec.expression}
                          </code>
                        )}
                        <div className="mt-1 font-tm-mono text-xs text-tm-muted">
                          {h.timestamp}
                          {h.isFavorite && (
                            <span className="ml-2 text-tm-warn">&#9733;</span>
                          )}
                        </div>
                      </TmRowButton>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)_176px] gap-3">
        <TmTextarea
          value={p.text}
          onChange={p.onTextChange}
          placeholder={t(locale, "alpha.placeholder" as Parameters<typeof t>[1])}
          aria-label={t(locale, "alpha.input.title" as Parameters<typeof t>[1])}
          rows={2}
          textareaClassName="min-h-[72px] bg-tm-bg px-4 py-3 text-[15px] leading-6"
          disabled={p.disabled}
        />
        <div className="grid min-h-[72px] grid-rows-2 gap-2">
          <TmButton
            type="button"
            size="md"
            onClick={p.onSubmit}
            disabled={p.disabled || empty}
            className="w-full"
          >
            <span aria-hidden="true">▷</span>
            {t(locale, "alpha.input.submitFull" as Parameters<typeof t>[1])}
          </TmButton>
          <TmButton
            type="button"
            variant="secondary"
            size="md"
            onClick={p.onRerun}
            disabled={p.disabled || !p.canRerun}
            title={locale === "zh" ? "保留当前表达式，使用下方最新参数重新回测" : "Keep the translated expression and rerun with the latest parameters"}
            className="w-full text-xs"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {locale === "zh" ? "按当前参数重测" : "Rerun current expression"}
          </TmButton>
        </div>
      </div>

      {/* Validation context is real request state, not decorative metadata. */}
      <div className="mt-3 flex items-end justify-between gap-4">
        <div className="font-tm-mono text-xs tabular-nums text-tm-muted">
          {p.text.length} {t(locale, "alpha.input.chars" as Parameters<typeof t>[1])}
        </div>

        <div className="grid flex-1 grid-cols-3 items-end gap-2 xl:grid-cols-[minmax(120px,1fr)_repeat(5,minmax(105px,0.75fr))_auto]">
          {/* Universe selector */}
          <TmSelect
            label={t(locale, "alpha.universe" as Parameters<typeof t>[1])}
            value={p.universe}
            onChange={(value) => p.onUniverseChange(value as FactorUniverse)}
            options={UNIVERSES.map((value) => ({ value, label: value }))}
          />

          <ValidationSelect label={locale === "zh" ? "策略方向" : "Direction"} value={p.validation.direction} onChange={(value) => updateValidation("direction", value as AlphaValidationParams["direction"])} options={["long_short", "long_only", "short_only"]} />
          <TmNumberInput label={locale === "zh" ? "分组比例" : "Bucket size"} min={5} max={50} step={5} value={p.validation.topPct} onChange={(value) => updateValidation("topPct", Math.min(50, Math.max(5, value)))} suffix="%" />
          <TmNumberInput label={locale === "zh" ? "成本模型" : "Round-trip cost"} min={0} max={200} value={p.validation.transactionCostBps} onChange={(value) => updateValidation("transactionCostBps", Math.min(200, Math.max(0, value)))} suffix="bps" />
          <ValidationSelect label={locale === "zh" ? "行业中性" : "Neutralize"} value={p.validation.neutralize} onChange={(value) => updateValidation("neutralize", value as AlphaValidationParams["neutralize"])} options={["none", "sector"]} />
          <ValidationSelect label={locale === "zh" ? "基准" : "Benchmark"} value={p.validation.benchmarkTicker} onChange={(value) => updateValidation("benchmarkTicker", value as AlphaValidationParams["benchmarkTicker"])} options={["SPY", "RSP"]} />

          {/* Browse examples — opens the example library modal (left of submit) */}
          {p.examples.length > 0 && (
            <TmButton
              type="button"
              variant="secondary"
              size="md"
              onClick={() => setExamplesOpen(true)}
            >
              <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span>
                {t(locale, "alpha.examples.browse" as Parameters<typeof t>[1])}
              </span>
            </TmButton>
          )}

        </div>
      </div>

      {/* Example library modal — collapsed behind the Browse examples button */}
      <FactorExampleModal
        open={examplesOpen}
        examples={p.examples}
        disabled={p.disabled}
        onSelect={(ex) => {
          p.onExampleSelect(ex);
          setExamplesOpen(false);
        }}
        onClose={() => setExamplesOpen(false)}
      />
    </section>
  );
}

function ValidationSelect({
  label,
  value,
  options,
  onChange,
}: {
  readonly label: string;
  readonly value: string;
  readonly options: readonly string[];
  readonly onChange: (value: string) => void;
}) {
  return (
    <TmSelect
      label={label}
      value={value}
      onChange={onChange}
      options={options.map((option) => ({
        value: option,
        label: option.replace("_", " "),
      }))}
    />
  );
}
