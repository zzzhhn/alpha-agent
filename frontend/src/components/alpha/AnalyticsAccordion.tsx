"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { HypothesisTranslateResponse } from "@/lib/types";

interface Props {
  translate: HypothesisTranslateResponse | null;
}

interface AutoFlags {
  degenerate: boolean;
}

function computeFlags(tr: HypothesisTranslateResponse): AutoFlags {
  return {
    degenerate: tr.smoke?.degenerate === true,
  };
}

// The additional panes that always appear under "Show more" regardless of flags.
// We ship 3 additional panes: smoke detail, llm provenance, operator usage.
const ADDITIONAL_PANE_COUNT = 3;

export function AnalyticsAccordion({ translate }: Props) {
  const { locale } = useLocale();
  const flags = useMemo<AutoFlags>(
    () => (translate ? computeFlags(translate) : { degenerate: false }),
    [translate],
  );

  const [showAll, setShowAll] = useState(false);

  if (!translate) return null;

  const autoExpandedCount = flags.degenerate ? 1 : 0;

  function accordionLabel(): string {
    if (autoExpandedCount > 0) {
      return showAll
        ? t(locale, "alpha.analytics.hideAdditional" as Parameters<typeof t>[1])
        : t(locale, "alpha.analytics.showMore" as Parameters<typeof t>[1]).replace("{n}", String(ADDITIONAL_PANE_COUNT));
    }
    return showAll
      ? t(locale, "alpha.analytics.hideAll" as Parameters<typeof t>[1])
      : t(locale, "alpha.analytics.showAll" as Parameters<typeof t>[1]).replace("{n}", String(ADDITIONAL_PANE_COUNT));
  }

  return (
    <section className="flex flex-col gap-2">
      {flags.degenerate && <DegenerateWarningPane translate={translate} />}

      <button
        onClick={() => setShowAll((s) => !s)}
        aria-label={accordionLabel()}
        className="inline-flex w-fit items-center gap-1 font-tm-mono text-xs text-tm-fg-2 hover:text-tm-fg"
      >
        {showAll ? (
          <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
        ) : (
          <ChevronRight className="h-3 w-3" strokeWidth={1.75} />
        )}
        {accordionLabel()}
      </button>

      {showAll && (
        <div className="flex flex-col gap-2">
          <SmokeDetailPane translate={translate} />
          <LlmProvenancePane translate={translate} />
          <OperatorUsagePane translate={translate} />
        </div>
      )}
    </section>
  );
}

// Auto-expanded when smoke.degenerate === true.
// Describes a degenerate factor (near-zero cross-sectional variance), NOT a lookahead leak.
function DegenerateWarningPane({
  translate,
}: {
  translate: HypothesisTranslateResponse;
}) {
  const { locale } = useLocale();
  return (
    <div className="rounded border border-tm-warn/40 bg-tm-warn/10 p-3 text-xs text-tm-warn">
      <div className="font-tm-mono font-semibold uppercase tracking-wide">
        {t(locale, "alpha.analytics.degenerateTitle" as Parameters<typeof t>[1])}
      </div>
      <div className="mt-1 font-tm-mono text-tm-fg-2">
        {t(locale, "alpha.analytics.degenerateWarningBody" as Parameters<typeof t>[1])}
      </div>
      <div className="mt-2 font-mono text-[11px] text-tm-muted">
        {t(locale, "alpha.analytics.degenerateFooter" as Parameters<typeof t>[1])}=
        {translate.smoke?.rows_valid ?? "n/a"}
        {" · "}
        factor_std=
        {translate.smoke?.factor_std !== undefined
          ? translate.smoke.factor_std.toFixed(4)
          : "n/a"}
      </div>
    </div>
  );
}

// Smoke probe numbers. Always shown under "Show more".
function SmokeDetailPane({
  translate,
}: {
  translate: HypothesisTranslateResponse;
}) {
  const { locale } = useLocale();
  const s = translate.smoke;
  if (!s) return null;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-tm-mono font-semibold uppercase tracking-wide text-tm-fg">
        {t(locale, "alpha.analytics.smokeDetail" as Parameters<typeof t>[1])}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-tm-mono">
        <div>
          ic_spearman:{" "}
          <span
            className={`font-mono ${s.ic_spearman >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
          >
            {s.ic_spearman.toFixed(4)}
          </span>
        </div>
        <div>
          {t(locale, "alpha.pane.rowsValid" as Parameters<typeof t>[1])}:{" "}
          <span className="font-mono text-tm-fg">{s.rows_valid}</span>
        </div>
        <div>
          {t(locale, "alpha.pane.runtime" as Parameters<typeof t>[1])}:{" "}
          <span className="font-mono text-tm-fg">{s.runtime_ms} ms</span>
        </div>
        {s.factor_std !== undefined && (
          <div>
            factor_std:{" "}
            <span
              className={`font-mono ${s.degenerate ? "text-tm-warn" : "text-tm-fg"}`}
            >
              {s.factor_std.toFixed(4)}
            </span>
          </div>
        )}
        {s.degenerate !== undefined && (
          <div>
            {t(locale, "alpha.analytics.degenerate" as Parameters<typeof t>[1])}:{" "}
            <span className={`font-mono ${s.degenerate ? "text-tm-warn" : "text-tm-pos"}`}>
              {s.degenerate ? "yes" : "no"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// LLM token usage. Built from translate.llm_tokens which is a real field.
// No provider or model info exists on HypothesisTranslateResponse; show token counts only.
function LlmProvenancePane({
  translate,
}: {
  translate: HypothesisTranslateResponse;
}) {
  const { locale } = useLocale();
  const { prompt, completion } = translate.llm_tokens;
  const total = prompt + completion;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-tm-mono font-semibold uppercase tracking-wide text-tm-fg">
        {t(locale, "alpha.analytics.llmProvenance" as Parameters<typeof t>[1])}
      </div>
      <div className="grid grid-cols-3 gap-x-4 gap-y-1 font-tm-mono">
        <div>
          prompt:{" "}
          <span className="font-mono text-tm-fg">{prompt.toLocaleString()}</span>
        </div>
        <div>
          completion:{" "}
          <span className="font-mono text-tm-fg">{completion.toLocaleString()}</span>
        </div>
        <div>
          total:{" "}
          <span className="font-mono text-tm-fg">{total.toLocaleString()}</span>
        </div>
      </div>
      <div className="mt-2 font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "alpha.analytics.llmTokenNote" as Parameters<typeof t>[1])}
      </div>
    </div>
  );
}

// Operators used in the current factor spec. Built from spec.operators_used.
function OperatorUsagePane({
  translate,
}: {
  translate: HypothesisTranslateResponse;
}) {
  const { locale } = useLocale();
  const ops = translate.spec.operators_used;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-tm-mono font-semibold uppercase tracking-wide text-tm-fg">
        {t(locale, "alpha.analytics.operatorUsage" as Parameters<typeof t>[1])}
      </div>
      {ops.length === 0 ? (
        <span className="font-tm-mono text-tm-muted">
          {t(locale, "alpha.analytics.opsEmpty" as Parameters<typeof t>[1])}
        </span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {ops.map((op) => (
            <span
              key={op}
              className="rounded-full border border-tm-rule px-2 py-0.5 font-mono text-[11px] text-tm-fg"
            >
              {op}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2 font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "alpha.analytics.opsNote" as Parameters<typeof t>[1])}
      </div>
    </div>
  );
}
