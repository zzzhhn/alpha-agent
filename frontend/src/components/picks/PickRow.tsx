import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import clsx from "clsx";
import WatchlistStar from "@/components/ui/WatchlistStar";
import { t, type Locale } from "@/lib/i18n";

const TIER_COLOR: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function PickRow({
  rank,
  card,
  watched = false,
  locale = "zh",
}: {
  rank: number;
  card: RatingCard;
  watched?: boolean;
  locale?: Locale;
}) {
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
        {watched ? <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" /> : null}
        <Link
          href={`/stock/${card.ticker}`}
          className="text-tm-accent hover:underline"
        >
          {card.ticker}
        </Link>
        {card.partial ? (
          <span
            className="ml-1.5 rounded bg-tm-bg-2 px-1 py-0.5 align-middle text-[8px] font-semibold uppercase tracking-wide text-tm-muted"
            title={t(locale, "picks_table.partial_tooltip")}
          >
            {t(locale, "picks_table.partial_badge")}
          </span>
        ) : null}
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
        {(card.top_drivers ?? []).slice(0, 3).join(" · ")}
      </td>
    </tr>
  );
}
