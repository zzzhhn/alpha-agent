import clsx from "clsx";
import { t, type Locale } from "@/lib/i18n";

// tm-* tokens are theme-aware (defined under [data-theme="light"] +
// dark default), so badge stays legible in both modes.
const TIER_COLOR: Record<string, string> = {
  BUY: "bg-tm-accent-soft text-tm-pos border-tm-pos",
  OW: "bg-tm-accent-soft text-tm-pos border-tm-pos/60",
  HOLD: "bg-tm-bg-3 text-tm-fg border-tm-rule-2",
  UW: "bg-tm-neg-soft text-tm-neg border-tm-neg/60",
  SELL: "bg-tm-neg-soft text-tm-neg border-tm-neg",
};

export default function RatingBadge({
  rating,
  confidence,
  agreement,
  composite,
  locale = "en",
}: {
  rating: string;
  // Calibrated directional hit-rate (honest edge). Shown small + secondary.
  confidence: number | null;
  // Raw signal-agreement (conviction). The primary bar + headline number.
  agreement?: number | null;
  composite: number | null;
  locale?: Locale;
}) {
  // NaN/Inf were sanitized to null at the storage boundary; coalesce to 0 here.
  const c = typeof composite === "number" && isFinite(composite) ? composite : 0;
  const hit =
    typeof confidence === "number" && isFinite(confidence) ? confidence : 0;
  // agreement is the headline; fall back to the calibrated value only on legacy
  // rows that predate the field (so the bar is never blank).
  const agr =
    typeof agreement === "number" && isFinite(agreement) && agreement > 0
      ? agreement
      : hit;
  // Below 0.5 the signal variance exceeds 1σ: the signals disagree more than
  // they agree. Flag it so a low-conviction call does not read as a clean one.
  const lowAgr = agr < 0.5;
  return (
    <div className="space-y-2">
      <div
        className={clsx(
          "inline-block rounded border px-3 py-1 text-sm font-bold",
          TIER_COLOR[rating] ?? "bg-zinc-700 text-zinc-200",
        )}
      >
        {rating} · composite {c >= 0 ? "+" : ""}
        {c.toFixed(2)}σ
      </div>
      <div className="space-y-0.5">
        {/* Primary: signal agreement (conviction). */}
        <div className="flex justify-between text-xs">
          <span
            className="text-tm-fg-2"
            title={t(locale, "rating.agreement_tooltip")}
          >
            {t(locale, "rating.agreement")}
          </span>
          <span
            className={clsx("font-mono", lowAgr ? "text-tm-warn" : "text-tm-fg")}
          >
            {(agr * 100).toFixed(0)}%
          </span>
        </div>
        <div className="h-1.5 w-full bg-tm-bg-3 rounded">
          <div
            className={clsx(
              "h-full rounded",
              lowAgr ? "bg-tm-warn" : "bg-tm-accent",
            )}
            style={{ width: `${agr * 100}%` }}
          />
        </div>
        {/* Secondary: calibrated historical directional hit-rate. */}
        <div
          className="flex justify-between pt-0.5 text-[11px] text-tm-muted"
          title={t(locale, "rating.hitrate_tooltip")}
        >
          <span>{t(locale, "rating.hitrate")}</span>
          <span className="font-mono">{(hit * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}
