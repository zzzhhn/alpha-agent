"use client";

import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import clsx from "clsx";
import { useLocale } from "@/components/layout/LocaleProvider";
import { getSuggestion } from "@/lib/suggestion";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import GradeStrip from "./GradeStrip";

/**
 * "★ Highest Conviction" hero band (ALPHACORE design, picks block lines
 * 882-894): surfaces the top-3 picks as decision-first cards above the full
 * table — the design system's "决策先行/金字塔" pattern (lead with the
 * conclusion + key numbers, demote the long list below).
 *
 * Honesty: the design mock shows a synthesized "why" sentence and a position
 * size. Neither exists as a real field, and the project forbids fabricated
 * data, so this derives the rationale from the REAL top_drivers (+ the
 * suggestion the row already computes) and shows the REAL agreement (signal
 * alignment) instead of inventing a position %.
 */

const TIER_COLOR: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function ConvictionBand({
  picks,
}: {
  readonly picks: readonly RatingCard[];
}) {
  const { locale } = useLocale();
  const top = picks.slice(0, 3);
  if (top.length === 0) return null;

  const copy =
    locale === "zh"
      ? { title: "高确信", agreement: "一致性", drivers: "驱动" }
      : { title: "HIGHEST CONVICTION", agreement: "agreement", drivers: "drivers" };

  return (
    <div className="px-4 pt-3">
      <div className="mb-2.5 font-tm-mono text-[11px] tracking-[0.12em] text-tm-accent">
        ★ {copy.title}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {top.map((card, i) => {
          const composite =
            typeof card.composite_score === "number" &&
            isFinite(card.composite_score)
              ? card.composite_score
              : 0;
          const hit =
            typeof card.confidence === "number" && isFinite(card.confidence)
              ? card.confidence
              : 0;
          const agr =
            typeof card.agreement === "number" &&
            isFinite(card.agreement) &&
            card.agreement > 0
              ? card.agreement
              : hit;
          const sug = getSuggestion(card.rating, hit, locale);
          const sugTone =
            sug.tone === "pos"
              ? "text-tm-pos"
              : sug.tone === "neg"
                ? "text-tm-neg"
                : "text-tm-fg-2";
          // The "why": the real drivers (top 2), in plain language — the same
          // signal→label map the table + radar use, so it stays consistent.
          const drivers = (card.top_drivers ?? [])
            .slice(0, 2)
            .map((s) => getSignalDisplayLabel(s, locale));

          return (
            <Link
              key={card.ticker + i}
              href={`/stock/${card.ticker}`}
              className="flex flex-col gap-2.5 border border-tm-rule bg-tm-bg-2 p-3.5 transition-colors hover:border-tm-accent hover:bg-tm-bg-3"
            >
              <div className="flex items-baseline justify-between">
                <span className="font-tm-mono text-[22px] font-bold text-tm-fg">
                  {card.ticker}
                </span>
                <span className="font-tm-mono text-base tabular-nums text-tm-accent">
                  {composite >= 0 ? "+" : ""}
                  {composite.toFixed(2)}σ
                </span>
              </div>
              <div className="min-h-[2.25rem] font-tm-sans text-[12.5px] leading-snug text-tm-fg-2">
                {drivers.length > 0 ? (
                  <>
                    <span className="text-tm-pos">↑ </span>
                    {drivers.join(" · ")}
                  </>
                ) : (
                  <span className="text-tm-muted">—</span>
                )}
              </div>
              <GradeStrip grades={card.dimension_grades ?? {}} locale={locale} />
              <div className="flex items-center justify-between border-t border-tm-rule pt-2">
                <span
                  className={clsx("font-tm-mono text-[12px] font-semibold", sugTone)}
                >
                  {sug.label}
                  {sug.caution ? <span className="ml-1 text-tm-warn">⚠</span> : null}
                </span>
                <span className="font-tm-mono text-[11px] text-tm-muted">
                  {copy.agreement}{" "}
                  <span className={clsx("tabular-nums", TIER_COLOR[card.rating] ?? "text-tm-fg-2")}>
                    {Math.round(agr * 100)}%
                  </span>
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
