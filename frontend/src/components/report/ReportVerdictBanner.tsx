"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { classifyFactorTier } from "@/lib/factor-tier";
import type { FactorBacktestResponse } from "@/lib/types";

/**
 * Report VERDICT banner (ALPHACORE design, report block lines 553-567): the
 * decision-first header above the tear sheet — leads with the factor, its
 * quality TIER, and the one-line intuition, so the conclusion is the first
 * thing read (the design's 金字塔 / pyramid principle).
 *
 * The tier is DERIVED from the result's own risk-attribution stats via the
 * canonical thresholds (classifyFactorTier), never a hand-label — so the banner
 * states exactly what the strict RISK.ATTRIBUTION test found, with no fabricated
 * verdict.
 */

const TONE_CLS: Record<string, string> = {
  pos: "text-tm-pos border-tm-pos",
  info: "text-tm-info border-tm-info",
  warn: "text-tm-warn border-tm-warn",
  muted: "text-tm-muted border-tm-muted",
};

export function ReportVerdictBanner({
  name,
  expression,
  intuition,
  backtest,
}: {
  readonly name: string;
  readonly expression: string;
  readonly intuition: string;
  readonly backtest: FactorBacktestResponse;
}) {
  const { locale } = useLocale();
  const tier = classifyFactorTier(backtest.alpha_pvalue, backtest.beta_market);
  const tag = locale === "zh" ? "因子" : "FACTOR";

  return (
    <section className="mb-3 flex flex-wrap items-start justify-between gap-4 border border-l-[3px] border-tm-accent bg-tm-accent-soft px-4 py-3.5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="bg-tm-accent px-1.5 py-0.5 font-tm-mono text-[9px] font-bold tracking-[0.16em] text-tm-bg">
            {tag}
          </span>
          <span className="font-tm-mono text-base font-bold text-tm-fg">
            {name}
          </span>
          <span
            className={`border px-2 py-px font-tm-mono text-[11px] font-bold tracking-[0.04em] ${
              TONE_CLS[tier.tone] ?? TONE_CLS.muted
            }`}
          >
            ★ {tier.label}
          </span>
        </div>
        <code className="mt-1.5 block break-all font-tm-mono text-[11.5px] text-tm-accent">
          {expression}
        </code>
        {intuition ? (
          <div className="mt-1.5 max-w-3xl text-[13px] leading-snug text-tm-fg">
            {intuition}
          </div>
        ) : null}
      </div>
    </section>
  );
}
