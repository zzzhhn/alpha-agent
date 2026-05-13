import clsx from "clsx";

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
  composite,
}: {
  rating: string;
  confidence: number | null;
  composite: number | null;
}) {
  // NaN/Inf were sanitized to null at the storage boundary; coalesce to 0 here.
  const c = typeof composite === "number" && isFinite(composite) ? composite : 0;
  const conf =
    typeof confidence === "number" && isFinite(confidence) ? confidence : 0;
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
        <div className="flex justify-between text-xs">
          <span className="text-tm-fg-2">confidence</span>
          <span className="text-tm-fg font-mono">{(conf * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 w-full bg-tm-bg-3 rounded">
          <div
            className="h-full bg-tm-accent rounded"
            style={{ width: `${conf * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
