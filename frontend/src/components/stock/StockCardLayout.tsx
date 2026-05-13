"use client";

import type { RatingCard } from "@/lib/api/picks";
import RatingBadge from "./RatingBadge";
import ActionBox from "./ActionBox";
import LeanThesis from "./LeanThesis";
import AttributionRadar from "./AttributionRadar";
import AttributionTable from "./AttributionTable";
import PriceChart from "./PriceChart";
import FundamentalsBlock from "./FundamentalsBlock";
import CatalystsBlock from "./CatalystsBlock";
import SourcesBlock from "./SourcesBlock";

export default function StockCardLayout({
  card,
  stale,
}: {
  card: RatingCard;
  stale: boolean;
}) {
  return (
    <div className="grid grid-cols-12 gap-6 px-4 py-6">
      {/* Left rail (sticky) */}
      <aside className="col-span-3 sticky top-4 self-start space-y-4">
        <div className="text-2xl font-bold">{card.ticker}</div>
        <RatingBadge
          rating={card.rating}
          confidence={card.confidence}
          composite={card.composite_score}
        />
        <ActionBox card={card} />
        <div className="text-xs text-zinc-500 space-y-0.5">
          <div>as of {new Date(card.as_of).toLocaleString()}</div>
          {stale ? (
            <div className="rounded bg-amber-500/15 px-2 py-1 text-amber-300">
              ⚠ data &gt; 24h old
            </div>
          ) : null}
        </div>
      </aside>

      {/* Right scroll */}
      <main className="col-span-9 space-y-8">
        <LeanThesis card={card} />
        <section>
          <h2 className="text-lg font-semibold mb-3">Signal Attribution</h2>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-4">
              <AttributionRadar card={card} />
            </div>
            <div className="col-span-8">
              <AttributionTable card={card} />
            </div>
          </div>
        </section>
        <PriceChart ticker={card.ticker} />
        <FundamentalsBlock card={card} />
        <CatalystsBlock card={card} />
        <SourcesBlock card={card} />
      </main>
    </div>
  );
}
