import clsx from "clsx";

const TIER_COLOR: Record<string, string> = {
  BUY: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  OW: "bg-emerald-500/10 text-emerald-200 border-emerald-500/30",
  HOLD: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  UW: "bg-rose-500/10 text-rose-200 border-rose-500/30",
  SELL: "bg-rose-500/20 text-rose-300 border-rose-500/40",
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
          <span className="text-zinc-400">confidence</span>
          <span>{(conf * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 w-full bg-zinc-800 rounded">
          <div
            className="h-full bg-blue-500 rounded"
            style={{ width: `${conf * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
