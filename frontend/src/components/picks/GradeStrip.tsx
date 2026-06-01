import clsx from "clsx";
import { DIMENSION_ORDER, gradeChipClass } from "@/lib/grade-colors";
import { t, type Locale } from "@/lib/i18n";

// Per-dimension i18n key for the chip tooltip. Keys live in i18n.ts under
// picks_table.dim_*; the strip stays single-line and the M/T/S/C/I/F legend
// is carried once by GradeStripHeader so every row's chips align under it.
const DIM_I18N: Record<string, string> = {
  Momentum: "picks_table.dim_momentum",
  Technical: "picks_table.dim_technical",
  Sentiment: "picks_table.dim_sentiment",
  Catalyst: "picks_table.dim_catalyst",
  Insider: "picks_table.dim_insider",
  Flow: "picks_table.dim_flow",
};

// Shared chip geometry so header legend + row chips line up to the pixel.
const CHIP_BASE =
  "inline-flex w-[20px] items-center justify-center rounded-sm py-0.5 font-tm-mono text-[9.5px] tabular-nums";

// A dimension is hidden when EVERY visible pick reports "—" for it (the
// backend returns "—" for a signal that has no cross-sectional data, e.g.
// Catalyst/Insider before their pipelines land). Hiding the whole column
// (header + cells) keeps the ribbon free of permanently-empty dead weight,
// and it auto-reappears the moment the signal starts producing data — no code
// change needed. Honest: not shown ≠ shown a fake grade.
export function computeHiddenDims(
  picks: { dimension_grades?: Record<string, string> | null }[],
): Set<string> {
  const hidden = new Set<string>();
  if (picks.length === 0) return hidden;
  for (const d of DIMENSION_ORDER) {
    const allDead = picks.every(
      (p) => (p.dimension_grades?.[d.key] ?? "—") === "—",
    );
    if (allDead) hidden.add(d.key);
  }
  return hidden;
}

export function GradeStripHeader({
  locale,
  hidden,
}: {
  locale: Locale;
  hidden?: ReadonlySet<string>;
}) {
  return (
    <div className="flex gap-0.5" aria-hidden>
      {DIMENSION_ORDER.filter((d) => !hidden?.has(d.key)).map((d) => (
        <span
          key={d.key}
          className={clsx(CHIP_BASE, "text-tm-muted")}
          title={t(locale, DIM_I18N[d.key] as never)}
        >
          {d.initial}
        </span>
      ))}
    </div>
  );
}

export default function GradeStrip({
  grades,
  locale,
  hidden,
}: {
  grades: Record<string, string>;
  locale: Locale;
  hidden?: ReadonlySet<string>;
}) {
  return (
    <div className="flex gap-0.5">
      {DIMENSION_ORDER.filter((d) => !hidden?.has(d.key)).map((d) => {
        const g = grades?.[d.key] ?? "—";
        const dimName = t(locale, DIM_I18N[d.key] as never);
        return (
          <span
            key={d.key}
            className={clsx(CHIP_BASE, gradeChipClass(g))}
            title={`${dimName}: ${g}`}
          >
            {g === "—" ? "·" : g}
          </span>
        );
      })}
    </div>
  );
}
