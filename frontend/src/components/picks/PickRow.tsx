import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import clsx from "clsx";

const TIER_COLOR: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function PickRow({ rank, card }: { rank: number; card: RatingCard }) {
  // Defensive: backend may return null for composite/confidence when legacy
  // DB rows held NaN before storage sanitization landed.
  const composite = typeof card.composite_score === "number" && isFinite(card.composite_score)
    ? card.composite_score
    : 0;
  const conf = typeof card.confidence === "number" && isFinite(card.confidence)
    ? card.confidence
    : 0;
  const sign = composite >= 0 ? "+" : "";
  return (
    <tr className="border-b border-tm-rule hover:bg-tm-bg-2 transition-colors">
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-muted tabular-nums">
        {rank}
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[11px] font-semibold">
        <Link
          href={`/stock/${card.ticker}`}
          className="text-tm-accent hover:underline"
        >
          {card.ticker}
        </Link>
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px]">
        <span className={clsx("font-semibold", TIER_COLOR[card.rating] ?? "text-tm-fg-2")}>
          {card.rating}
        </span>
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] tabular-nums text-right">
        {sign}{composite.toFixed(2)}σ
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] tabular-nums text-right">
        {(conf * 100).toFixed(0)}%
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-muted">
        {card.top_drivers.slice(0, 3).join(" · ")}
      </td>
    </tr>
  );
}
