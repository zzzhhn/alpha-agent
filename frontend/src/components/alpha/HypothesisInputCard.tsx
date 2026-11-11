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
const UNIVERSES: FactorUniverse[] = ["SP500"];

// ---- Component ----

export function HypothesisInputCard(p: Props) {
  const { locale } = useLocale();
  const zh = locale === "zh";
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
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setHistoryOpen(false);
        popoverRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [historyOpen]);

  const empty = p.text.trim().length === 0;
  const updateValidation = <K extends keyof AlphaValidationParams>(
    key: K,
    value: AlphaValidationParams[K],
  ) => p.onValidationChange({ ...p.validation, [key]: value });

  return (
    <section className="alpha-composer border-b border-tm-rule">
      <div className="alpha-thesis">
      {/* Header row: section title + History popover trigger */}
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-tm-fg">
          <span className="mr-2 text-tm-accent">①</span>
          {t(locale, "alpha.input.title" as Parameters<typeof t>[1])}
        </h2>
        <div className="flex items-center gap-2">
          {p.examples.length > 0 && (
            <TmButton type="button" variant="secondary" disabled={p.disabled} onClick={() => setExamplesOpen(true)}>
              <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.75} />
              {t(locale, "alpha.examples.browse" as Parameters<typeof t>[1])}
            </TmButton>
          )}
        {/* History popover */}
        <div className="relative" ref={popoverRef}>
          <TmButton
            type="button"
            variant="secondary"
            onClick={() => setHistoryOpen((o) => !o)}
            disabled={p.disabled}
            aria-expanded={historyOpen}
            aria-controls="alpha-input-history"
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
            <div id="alpha-input-history" className="absolute right-0 top-full z-10 mt-1 max-h-[400px] w-[380px] max-w-[80vw] overflow-y-auto rounded-[2px] border border-tm-rule bg-tm-bg-2 shadow-[var(--tm-shadow-floating)]">
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
        </div>
      </header>
      <div>
        <TmTextarea
          value={p.text}
          onChange={p.onTextChange}
          placeholder={t(locale, "alpha.placeholder" as Parameters<typeof t>[1])}
          aria-label={t(locale, "alpha.input.title" as Parameters<typeof t>[1])}
          rows={3}
          textareaClassName="min-h-[116px] resize-y bg-tm-bg-2 px-4 py-3 text-sm leading-6"
          disabled={p.disabled}
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs tabular-nums text-tm-muted">{p.text.length} {t(locale, "alpha.input.chars" as Parameters<typeof t>[1])}</span>
          {/* Translation is the only paid step here; the backtest itself does not call a model. */}
          <span className="text-xs text-tm-muted">{zh ? "翻译会用你的模型密钥调用一次模型（按你的服务商计费）；回测本身不调用模型。" : "Translation calls your configured model once (billed by your provider); the backtest itself does not call a model."}</span>
          <div className="flex flex-wrap items-center gap-2">
          {p.canRerun && (
            <TmButton type="button" variant="secondary" size="md" onClick={p.onRerun} disabled={p.disabled}
              title={zh ? "保留当前表达式，使用当前参数重新回测" : "Keep the expression and rerun with the current parameters"}>
              <RotateCcw className="h-3.5 w-3.5" />
              {zh ? "按当前参数重测" : "Rerun expression"}
            </TmButton>
          )}
          <TmButton
            type="button"
            size="md"
            onClick={p.onSubmit}
            disabled={p.disabled || empty}
            className="min-w-40"
          >
            <span aria-hidden="true">▷</span>
            {t(locale, "alpha.input.submitFull" as Parameters<typeof t>[1])}
          </TmButton>
          </div>
        </div>
      </div>
      </div>
      {/* Validation context is real request state, not decorative metadata. */}
      <fieldset disabled={p.disabled} className="alpha-validation min-w-0">
        <legend className="sr-only">{zh ? "验证参数" : "Validation parameters"}</legend>
        <h3 className="mb-3 text-sm font-semibold text-tm-fg">{zh ? "验证参数" : "Validation parameters"}</h3>
        <div className="grid grid-cols-2 items-end gap-x-4 gap-y-3">
          {/* Universe selector */}
          <TmSelect
            label={zh ? "股票池" : "Universe"}
            hint={zh ? "当前验证仅支持 S&P 500" : "Validation currently supports S&P 500 only"}
            value={p.universe}
            onChange={(value) => p.onUniverseChange(value as FactorUniverse)}
            options={UNIVERSES.map((value) => ({ value, label: value === "SP500" ? "S&P 500" : zh ? "自定义" : "Custom" }))}
          />

          <ValidationSelect label={locale === "zh" ? "策略方向" : "Direction"} value={p.validation.direction} onChange={(value) => updateValidation("direction", value as AlphaValidationParams["direction"])} options={["long_short", "long_only", "short_only"]} />
          <TmNumberInput className="alpha-number" label={locale === "zh" ? "分组比例" : "Bucket size"} min={5} max={50} step={5} value={p.validation.topPct} onChange={(value) => updateValidation("topPct", Math.min(50, Math.max(5, value)))} suffix="%" />
          <TmNumberInput className="alpha-number" label={locale === "zh" ? "成本模型" : "Round-trip cost"} min={0} max={200} value={p.validation.transactionCostBps} onChange={(value) => updateValidation("transactionCostBps", Math.min(200, Math.max(0, value)))} suffix="bps" />
          <ValidationSelect label={locale === "zh" ? "行业中性" : "Neutralize"} value={p.validation.neutralize} onChange={(value) => updateValidation("neutralize", value as AlphaValidationParams["neutralize"])} options={["none", "sector"]} />
          <ValidationSelect label={locale === "zh" ? "基准" : "Benchmark"} value={p.validation.benchmarkTicker} onChange={(value) => updateValidation("benchmarkTicker", value as AlphaValidationParams["benchmarkTicker"])} options={["SPY", "RSP"]} />

        </div>
      </fieldset>

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
  const { locale } = useLocale();
  const labels: Record<string, string> = locale === "zh"
    ? { long_short: "多空", long_only: "只做多", short_only: "只做空", none: "不中性化", sector: "行业中性" }
    : { long_short: "Long / short", long_only: "Long only", short_only: "Short only", none: "None", sector: "Sector" };
  return (
    <TmSelect
      label={label}
      value={value}
      onChange={onChange}
      options={options.map((option) => ({
        value: option,
        label: labels[option] ?? option,
      }))}
    />
  );
}
