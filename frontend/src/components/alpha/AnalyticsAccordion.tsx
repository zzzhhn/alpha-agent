"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import type { HypothesisTranslateResponse } from "@/lib/types";

interface Props {
  translate: HypothesisTranslateResponse | null;
}

interface AutoFlags {
  degenerate: boolean;
}

function computeFlags(t: HypothesisTranslateResponse): AutoFlags {
  return {
    degenerate: t.smoke?.degenerate === true,
  };
}

// The additional panes that always appear under "Show more" regardless of flags.
// We ship 3 additional panes: smoke detail, llm provenance, operator usage.
const ADDITIONAL_PANE_COUNT = 3;

export function AnalyticsAccordion({ translate }: Props) {
  const flags = useMemo<AutoFlags>(
    () => (translate ? computeFlags(translate) : { degenerate: false }),
    [translate],
  );

  const [showAll, setShowAll] = useState(false);

  if (!translate) return null;

  const autoExpandedCount = flags.degenerate ? 1 : 0;

  return (
    <section className="flex flex-col gap-2">
      {flags.degenerate && <DegenerateWarningPane translate={translate} />}

      <button
        onClick={() => setShowAll((s) => !s)}
        className="inline-flex w-fit items-center gap-1 text-xs text-tm-fg-2 hover:text-tm-fg"
      >
        {showAll ? (
          <ChevronDown className="h-3 w-3" strokeWidth={1.75} />
        ) : (
          <ChevronRight className="h-3 w-3" strokeWidth={1.75} />
        )}
        {autoExpandedCount > 0
          ? showAll
            ? "Hide additional analysis"
            : `Show ${ADDITIONAL_PANE_COUNT} more analysis panes`
          : showAll
          ? `Hide analysis (${ADDITIONAL_PANE_COUNT} panes)`
          : `Show analysis (${ADDITIONAL_PANE_COUNT} panes)`}
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
  return (
    <div className="rounded border border-tm-warn/40 bg-tm-warn/10 p-3 text-xs text-tm-warn">
      <div className="font-semibold uppercase tracking-wide">
        Degenerate factor warning
      </div>
      <div className="mt-1 text-tm-fg-2">
        The smoke probe detected a degenerate factor. Cross-sectional variance
        is near zero, meaning the factor assigns nearly identical values to
        all stocks in the universe. Downstream backtest metrics such as IC and
        Sharpe are unreliable when the signal has no spread. Common causes:
        constant feature input, division by a near-zero denominator, or a
        cross-sectional operation applied to a universe that is too small.
      </div>
      <div className="mt-2 text-[11px] text-tm-muted">
        rows_valid={translate.smoke?.rows_valid ?? "n/a"}
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
  const s = translate.smoke;
  if (!s) return null;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-semibold uppercase tracking-wide text-tm-fg">
        Smoke detail
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <div>
          ic_spearman:{" "}
          <span
            className={
              s.ic_spearman >= 0 ? "text-tm-pos" : "text-tm-neg"
            }
          >
            {s.ic_spearman.toFixed(4)}
          </span>
        </div>
        <div>
          rows_valid: <span className="text-tm-fg">{s.rows_valid}</span>
        </div>
        <div>
          runtime: <span className="text-tm-fg">{s.runtime_ms} ms</span>
        </div>
        {s.factor_std !== undefined && (
          <div>
            factor_std:{" "}
            <span
              className={
                s.degenerate ? "text-tm-warn" : "text-tm-fg"
              }
            >
              {s.factor_std.toFixed(4)}
            </span>
          </div>
        )}
        {s.degenerate !== undefined && (
          <div>
            degenerate:{" "}
            <span className={s.degenerate ? "text-tm-warn" : "text-tm-pos"}>
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
  const { prompt, completion } = translate.llm_tokens;
  const total = prompt + completion;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-semibold uppercase tracking-wide text-tm-fg">
        LLM token usage
      </div>
      <div className="grid grid-cols-3 gap-x-4 gap-y-1">
        <div>
          prompt: <span className="text-tm-fg">{prompt.toLocaleString()}</span>
        </div>
        <div>
          completion:{" "}
          <span className="text-tm-fg">{completion.toLocaleString()}</span>
        </div>
        <div>
          total: <span className="text-tm-fg">{total.toLocaleString()}</span>
        </div>
      </div>
      <div className="mt-2 text-[11px] text-tm-muted">
        Token counts are for this translation run only. Provider and model
        are determined by your BYOK configuration and are not included in
        the server response.
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
  const ops = translate.spec.operators_used;
  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 p-3 text-xs text-tm-fg-2">
      <div className="mb-2 font-semibold uppercase tracking-wide text-tm-fg">
        Operator usage
      </div>
      {ops.length === 0 ? (
        <span className="text-tm-muted">none detected</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {ops.map((op) => (
            <span
              key={op}
              className="rounded-full border border-tm-rule px-2 py-0.5 text-[11px] text-tm-fg"
            >
              {op}
            </span>
          ))}
        </div>
      )}
      <div className="mt-2 text-[11px] text-tm-muted">
        Operators extracted from the translated expression for this spec.
        Full frequency ranking across history is available in the
        Operator.Usage pane on the main analytics panel.
      </div>
    </div>
  );
}
