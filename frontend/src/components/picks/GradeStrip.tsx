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

export function GradeStripHeader({ locale }: { locale: Locale }) {
  return (
    <div className="flex gap-0.5" aria-hidden>
      {DIMENSION_ORDER.map((d) => (
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
}: {
  grades: Record<string, string>;
  locale: Locale;
}) {
  return (
    <div className="flex gap-0.5">
      {DIMENSION_ORDER.map((d) => {
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
