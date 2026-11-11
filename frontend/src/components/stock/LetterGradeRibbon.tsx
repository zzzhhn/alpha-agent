"use client";

/**
 * B8 (2026-05-19) per-dimension letter grade ribbon.
 *
 * Six dimensions (Momentum / Technical / Sentiment / Catalyst / Insider /
 * Flow) each show an A+ to F grade computed server-side from the
 * breakdown z-scores. Sits below GexBadge / above ActionBox in the
 * StockCardLayout sidebar so the user reads SeekingAlpha-style
 * at-a-glance before drilling into the AttributionTable.
 *
 * Color rubric: A+/A green, B/C+ neutral, C muted, D/F red. "—" for
 * dimensions whose constituent signals are absent (e.g. options when
 * the chain didn't load).
 */

import type { GradeMethod } from "@/lib/api/picks";
import { gradeExplanation, gradeDimensionLabel } from "@/lib/grade-method";
import { TmTooltip } from "@/components/tm/TmTooltip";
import GradeLegend from "@/components/picks/GradeLegend";
import type { Locale } from "@/lib/i18n";

const GRADE_TONE: Record<string, string> = {
  "A+": "text-tm-pos border-tm-pos/40 bg-tm-pos/10",
  A: "text-tm-pos border-tm-pos/30 bg-tm-pos/5",
  B: "text-tm-fg border-tm-rule bg-tm-bg-3",
  "C+": "text-tm-fg-2 border-tm-rule bg-tm-bg-3",
  C: "text-tm-muted border-tm-rule bg-tm-bg-3",
  D: "text-tm-neg border-tm-neg/30 bg-tm-neg/5",
  F: "text-tm-neg border-tm-neg/40 bg-tm-neg/10",
  "—": "text-tm-muted border-tm-rule bg-tm-bg-2",
};

const DIMENSION_LABELS: Record<string, Record<Locale, string>> = {
  Momentum: { zh: "动量", en: "MOM" },
  Technical: { zh: "技术", en: "TECH" },
  Sentiment: { zh: "情绪", en: "SENT" },
  Catalyst: { zh: "催化", en: "CAT" },
  Insider: { zh: "内部", en: "INS" },
  Flow: { zh: "资金", en: "FLOW" },
};

const DIMENSION_ORDER: string[] = [
  "Momentum",
  "Technical",
  "Sentiment",
  "Catalyst",
  "Insider",
  "Flow",
];

export default function LetterGradeRibbon({
  grades, scores, method,
  locale,
}: {
  grades: Record<string, string>;
  scores?: Record<string, number | null> | null;
  method?: GradeMethod;
  locale: Locale;
}) {
  if (!grades || Object.keys(grades).length === 0) return null;

  return (
    <div className="rounded-[2px] border border-tm-rule bg-tm-bg-2 p-2">
      <div className="mb-1 text-xs uppercase tracking-wide text-tm-muted font-tm-sans">
        <GradeLegend method={method} locale={locale} />
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6 lg:grid-cols-3">
        {DIMENSION_ORDER.map((dim) => {
          const grade = grades[dim] ?? "—";
          const tone = GRADE_TONE[grade] ?? GRADE_TONE["—"];
          const label = DIMENSION_LABELS[dim]?.[locale] ?? dim;
          return (
            <TmTooltip key={dim} width={280} content={gradeExplanation(gradeDimensionLabel(dim, locale === "zh"), grade, scores?.[dim], method, locale === "zh")} className="justify-center">
            <div className={`flex w-full flex-col items-center rounded-[2px] border ${tone} px-1 py-0.5`}>
              <span className="whitespace-nowrap text-xs font-tm-sans text-tm-fg-2">{label}</span>
              <span className="text-sm font-semibold font-tm-sans">{grade}</span>
            </div>
            </TmTooltip>
          );
        })}
      </div>
    </div>
  );
}
